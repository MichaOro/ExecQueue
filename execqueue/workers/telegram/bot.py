"""Telegram bot self-health reporting."""

import asyncio
import inspect
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from execqueue.db.session import create_session
from execqueue.settings import get_settings
from execqueue.workers.telegram import auth as telegram_auth
from execqueue.workers.telegram.commands import (
    create_cancel,
    create_prompt,
    create_start,
    create_task_type,
    create_title,
    get_health_command_message,
    get_help_message,
    get_start_message,
    status_command,
)
from execqueue.workers.telegram.notifications import (
    build_startup_message,
    get_startup_notification_recipients,
)
from execqueue.workers.telegram.persistence import upsert_telegram_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from telegram import Bot, Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ConversationHandler,
        ContextTypes,
        MessageHandler,
    )
    from telegram.ext import filters as Filters

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = None  # type: ignore
    Application = None  # type: ignore
    CommandHandler = None  # type: ignore
    ConversationHandler = None  # type: ignore
    ContextTypes = None  # type: ignore
    MessageHandler = None  # type: ignore
    Filters = None  # type: ignore
    Update = None  # type: ignore


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
HEALTH_FILE = PROJECT_ROOT / "ops" / "health" / "telegram_bot.json"
PID_FILE = PROJECT_ROOT / "ops" / "pids" / "telegram_bot.pid"

# Conversation states for /create (imported from commands but re-exported here for registration)
from execqueue.workers.telegram.commands import (
    CREATE_PROMPT,
    CREATE_TASK_TYPE,
    CREATE_TITLE,
)


def persist_message_user(update: Update) -> None:
    """Persist Telegram user metadata without blocking command responses on failure."""
    telegram_user = getattr(update, "effective_user", None)
    telegram_user_id = getattr(telegram_user, "id", None)
    if telegram_user is None or not isinstance(telegram_user_id, int):
        return

    session = create_session()
    try:
        upsert_telegram_user(
            session,
            telegram_id=telegram_user_id,
            first_name=getattr(telegram_user, "first_name", None),
            last_name=getattr(telegram_user, "last_name", None),
        )
    except Exception:
        logger.exception("Failed to persist Telegram user %s", telegram_user_id)
    finally:
        session.close()


def write_health_status(status: str, detail: str = "", include_pid: bool = False) -> None:
    """Write bot health status to file for API consumption."""
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)

    health_data = {
        "component": "telegram_bot",
        "status": status,
        "detail": detail,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }

    if include_pid:
        health_data["pid"] = os.getpid()

    try:
        HEALTH_FILE.write_text(json.dumps(health_data, indent=2))
        logger.debug("Health status written: %s", status)
    except Exception as exc:
        logger.error("Failed to write health status: %s", exc)


async def _await_if_needed(value: object) -> None:
    """Await values only when the underlying Telegram client returns a coroutine."""
    if inspect.isawaitable(value):
        await value


async def _event_is_set(event: asyncio.Event) -> bool:
    """Support both real asyncio events and mocked async event helpers in tests."""
    value = event.is_set()
    if inspect.isawaitable(value):
        return bool(await value)
    return bool(value)


def write_pid_file(pid: int | None = None) -> None:
    """Persist the current bot PID for restart orchestration."""
    pid_value = os.getpid() if pid is None else pid
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(f"{pid_value}\n", encoding="utf-8")


def clear_pid_file(expected_pid: int | None = None) -> None:
    """Remove the PID file when it belongs to the current bot process."""
    try:
        recorded_pid = PID_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return
    except Exception as exc:
        logger.warning("Failed to read Telegram bot PID file before cleanup: %s", exc)
        recorded_pid = ""

    if expected_pid is not None and recorded_pid:
        try:
            if int(recorded_pid) != expected_pid:
                logger.debug(
                    "Skipping PID file cleanup because it belongs to another process: %s",
                    recorded_pid,
                )
                return
        except ValueError:
            logger.warning("Telegram bot PID file contained an invalid PID: %s", recorded_pid)

    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to remove Telegram bot PID file: %s", exc)


async def stop_bot_application(
    application: "Application",
    shutdown_event: asyncio.Event,
    timeout: int,
) -> None:
    """Stop the Telegram application within a bounded timeout."""

    async def _shutdown_steps() -> None:
        updater = getattr(application, "updater", None)
        if updater is not None and hasattr(updater, "stop"):
            await _await_if_needed(updater.stop())

        if hasattr(application, "stop"):
            await _await_if_needed(application.stop())

        if hasattr(application, "shutdown"):
            await _await_if_needed(application.shutdown())

    write_health_status("not_ok", "Telegram bot is shutting down.", include_pid=True)

    try:
        await asyncio.wait_for(_shutdown_steps(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("Telegram bot shutdown timed out after %s seconds.", timeout)
        write_health_status(
            "not_ok",
            f"Telegram bot shutdown timed out after {timeout} seconds.",
            include_pid=True,
        )
    except Exception:
        logger.exception("Failed to shut down Telegram bot cleanly")
        write_health_status(
            "not_ok",
            "Telegram bot encountered an error during shutdown.",
            include_pid=True,
        )
    finally:
        clear_pid_file(expected_pid=os.getpid())
        await _await_if_needed(shutdown_event.set())


def create_shutdown_handler(
    loop: asyncio.AbstractEventLoop,
    application: "Application",
    shutdown_event: asyncio.Event,
    timeout: int,
):
    """Create a signal-safe handler that delegates shutdown work to the event loop."""
    shutdown_task: asyncio.Task[None] | None = None

    def shutdown_handler() -> None:
        nonlocal shutdown_task

        if shutdown_task is not None and not shutdown_task.done():
            logger.info("Shutdown already in progress, ignoring duplicate signal.")
            return

        logger.info("Shutdown signal received, stopping bot...")
        shutdown_task = loop.create_task(
            stop_bot_application(
                application=application,
                shutdown_event=shutdown_event,
                timeout=timeout,
            )
        )

    return shutdown_handler


async def start_command(update: Update, context: "ContextTypes.DEFAULT_TYPE | None") -> None:
    """Handle /start command."""
    persist_message_user(update)
    telegram_user_id = update.effective_user.id if update.effective_user else None
    role = None
    is_active = False

    if telegram_user_id:
        try:
            role, is_active = telegram_auth.get_user_info(telegram_user_id)
        except Exception:
            logger.exception("Failed to check user role for start command")

    if update.message:
        await update.message.reply_text(
            get_start_message(role=role, is_active=is_active)
        )


async def help_command(update: Update, context: "ContextTypes.DEFAULT_TYPE | None") -> None:
    """Handle /help command - shows commands with role-based filtering."""
    if not update.message:
        return

    # Get user's role from database using auth helper
    telegram_user_id = update.effective_user.id if update.effective_user else None
    role = None
    is_active = False

    if telegram_user_id:
        try:
            role, is_active = telegram_auth.get_user_info(telegram_user_id)
        except Exception:
            logger.exception("Failed to check user role for help command")

    await update.message.reply_text(
        get_help_message(role=role, is_active=is_active),
        parse_mode="Markdown",
    )


async def health_command(
    update: Update, context: "ContextTypes.DEFAULT_TYPE | None"
) -> None:
    """Handle /health command."""
    if update.message:
        await update.message.reply_text(get_health_command_message())


async def restart_command(
    update: Update, context: "ContextTypes.DEFAULT_TYPE | None"
) -> None:
    """Handle /restart command - Admin only.
    
    Supports:
    - /restart - System restart (API + Bot)
    - /restart acp - ACP restart only
    - /restart all - Full restart (API + Bot + ACP)
    """
    if not update.message:
        return

    # Check if user is admin
    telegram_user_id = update.effective_user.id if update.effective_user else None
    is_admin = False

    if telegram_user_id:
        try:
            role, is_active = telegram_auth.get_user_info(telegram_user_id)
            is_admin = is_active and role == "admin"
        except Exception:
            logger.exception("Failed to check user role for restart command")

    if not is_admin:
        await update.message.reply_text(
            "Zugriff verweigert. Dieser Befehl ist nur fuer Administratoren verfuegbar."
        )
        return

    # Parse restart type argument
    restart_type = "system"  # default
    if context and context.args:
        arg = context.args[0].lower()
        if arg in ("acp", "all"):
            restart_type = arg
        else:
            await update.message.reply_text(
                "*Ungueltiger Parameter*\n\n"
                "Verfuegbare Optionen:\n"
                "/restart - System neu starten (API + Bot)\n"
                "/restart acp - ACP neu starten\n"
                "/restart all - Alle Komponenten neu starten",
                parse_mode="Markdown"
            )
            return

    # Send confirmation based on restart type
    if restart_type == "acp":
        await update.message.reply_text(
            "*ACP-Neustart wird vorbereitet...*\n\n"
            "Sende Anfrage an API. Dies kann einen Moment dauern.",
            parse_mode="Markdown"
        )
    elif restart_type == "all":
        await update.message.reply_text(
            "*Vollstaendiger Neustart wird vorbereitet...*\n\n"
            "Sende Anfrage an API. Dies kann einen Moment dauern.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "*System-Neustart wird vorbereitet...*\n\n"
            "Sende Anfrage an API. Dies kann einen Moment dauern.",
            parse_mode="Markdown"
        )

    # Trigger appropriate restart via API (async, don't block)
    from execqueue.workers.telegram.commands import (
        trigger_acp_restart,
        trigger_system_restart,
        trigger_system_restart_all,
    )

    try:
        if restart_type == "acp":
            success, message = await trigger_acp_restart()
        elif restart_type == "all":
            success, message = await trigger_system_restart_all()
        else:
            success, message = await trigger_system_restart()
        
        if success:
            await update.message.reply_text(
                f"*Neustart erfolgreich ausgeloest*\n\n{message}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"*Neustart fehlgeschlagen*\n\n{message}",
                parse_mode="Markdown"
            )
    except Exception:
        logger.exception("Error during restart command")
        await update.message.reply_text(
            "*Fehler beim Neustart*\n\nEin unerwarteter Fehler ist aufgetreten. Bitte Logs oder Health pruefen.",
            parse_mode="Markdown"
        )


async def send_notification_to_user(user_id: str, message: str) -> bool:
    """Send a notification message to a specific Telegram user."""
    settings = get_settings()

    if not user_id:
        logger.debug("No user ID configured, skipping notification")
        return False

    if not TELEGRAM_AVAILABLE:
        logger.error("Cannot send notification: python-telegram-bot not installed")
        return False

    try:
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown",
        )
        logger.info("Notification sent to user %s", user_id)
        return True
    except Exception as exc:
        logger.error("Failed to send notification to user %s: %s", user_id, exc)
        return False


async def send_notification_to_channel(message: str) -> bool:
    """Send a notification message to the configured notification user.

    Deprecated: Use send_startup_notification() for DB-based subscriber notifications.
    This function remains for backward compatibility with legacy notifications.
    """
    settings = get_settings()

    if not settings.telegram_notification_user_id:
        logger.debug("Notification user not configured, skipping notification")
        return False

    return await send_notification_to_user(settings.telegram_notification_user_id, message)


async def send_startup_notification() -> None:
    """Send startup notification to all subscribed active users.

    Queries database for active users subscribed to TELEGRAM_NOTIFICATION_STARTUP.
    Fully DB-based - no legacy ENV fallback.
    """
    if not TELEGRAM_AVAILABLE:
        logger.error("Cannot send startup notification: python-telegram-bot not installed")
        return

    settings = get_settings()
    message = build_startup_message()

    # Send to DB-subscribed users only
    session = create_session()
    try:
        recipient_ids = get_startup_notification_recipients(session)
    finally:
        session.close()

    if not recipient_ids:
        logger.debug("No DB-subscribed users found for startup notification")
        return

    logger.info("Sending startup notification to %d subscribed users", len(recipient_ids))

    # Create bot instance for sending notifications
    try:
        bot = Bot(token=settings.telegram_bot_token)
        for user_id in recipient_ids:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="Markdown",
                )
                logger.info("Startup notification sent to user %s", user_id)
            except Exception:
                logger.exception("Failed to send startup notification to user %s", user_id)
    except Exception:
        logger.exception("Failed to create bot instance for startup notifications")


def create_bot_application(token: str, polling_timeout: int) -> Application:
    """Create and configure the Telegram bot application."""
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("restart", restart_command))

    # Task-related commands
    application.add_handler(CommandHandler("status", status_command))

    # /create conversation handler
    create_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create", create_start)],
        states={
            CREATE_TASK_TYPE: [
                MessageHandler(Filters.TEXT & ~Filters.COMMAND, create_task_type)
            ],
            CREATE_TITLE: [
                MessageHandler(Filters.TEXT & ~Filters.COMMAND, create_title)
            ],
            CREATE_PROMPT: [
                MessageHandler(Filters.TEXT & ~Filters.COMMAND, create_prompt)
            ],
        },
        fallbacks=[CommandHandler("cancel", create_cancel)],
    )
    application.add_handler(create_conv_handler)

    return application


async def health_reporter(polling_timeout: int) -> None:
    """Periodically update the bot health file."""
    while True:
        try:
            write_health_status(
                "ok",
                "Telegram bot is running and polling for updates.",
                include_pid=True,
            )
        except Exception as exc:
            logger.error("Health reporter error: %s", exc)

        await asyncio.sleep(polling_timeout)


async def run_bot() -> None:
    """Run the Telegram bot with polling and health reporting."""
    settings = get_settings()

    if not settings.telegram_bot_enabled:
        logger.info("Telegram bot is disabled (TELEGRAM_BOT_ENABLED=false)")
        write_health_status("not_ok", "Telegram bot is disabled.")
        return

    if not settings.telegram_bot_token:
        logger.error(
            "Telegram bot is enabled but TELEGRAM_BOT_TOKEN is not set. "
            "Please configure the bot token in your environment."
        )
        write_health_status("not_ok", "Telegram bot enabled but token not set.")
        sys.exit(1)

    if not TELEGRAM_AVAILABLE:
        logger.error(
            "python-telegram-bot is not installed. "
            "Please install it with: pip install python-telegram-bot"
        )
        write_health_status("not_ok", "python-telegram-bot library not installed.")
        sys.exit(1)

    logger.info("Starting Telegram bot with polling and health reporting...")
    write_health_status("starting", "Telegram bot is initializing...", include_pid=True)

    application = create_bot_application(
        token=settings.telegram_bot_token,
        polling_timeout=settings.telegram_polling_timeout,
    )

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    shutdown_handler = create_shutdown_handler(
        loop=loop,
        application=application,
        shutdown_event=shutdown_event,
        timeout=settings.telegram_shutdown_timeout,
    )

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            signal.signal(sig, lambda sig, frame: shutdown_handler())

    await application.initialize()
    await application.start()
    write_pid_file()

    logger.info("Bot started successfully. Press Ctrl+C to stop.")
    health_task: asyncio.Task[None] | None = None

    try:
        try:
            await send_startup_notification()
        except Exception:
            logger.exception("Failed to send startup notification, but bot continues running")

        health_task = asyncio.create_task(health_reporter(settings.telegram_polling_timeout))

        await application.updater.start_polling(
            timeout=settings.telegram_polling_timeout,
            allowed_updates=Update.ALL_TYPES,
        )
        write_health_status(
            "ok",
            "Telegram bot is running and polling for updates.",
            include_pid=True,
        )
        await shutdown_event.wait()
    except asyncio.CancelledError:
        logger.info("Telegram bot task cancelled, shutting down...")
        if not await _event_is_set(shutdown_event):
            await stop_bot_application(
                application=application,
                shutdown_event=shutdown_event,
                timeout=settings.telegram_shutdown_timeout,
            )
        raise
    finally:
        if health_task is not None:
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass

        if not await _event_is_set(shutdown_event):
            await stop_bot_application(
                application=application,
                shutdown_event=shutdown_event,
                timeout=settings.telegram_shutdown_timeout,
            )

        write_health_status("not_ok", "Telegram bot stopped.", include_pid=True)


def main() -> None:
    """Main entry point for the Telegram bot."""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        write_health_status("not_ok", "Telegram bot stopped by user.", include_pid=True)
    except Exception:
        logger.exception("Bot encountered a fatal error")
        write_health_status(
            "not_ok",
            "Telegram bot encountered a fatal error.",
            include_pid=True,
        )
        sys.exit(1)
    finally:
        clear_pid_file(expected_pid=os.getpid())


if __name__ == "__main__":
    main()
