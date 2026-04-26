"""Telegram bot self-health reporting."""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from execqueue.db.session import create_session
from execqueue.settings import get_settings
from execqueue.workers.telegram.commands import (
    get_health_command_message,
    get_start_message,
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
    from telegram.ext import Application, CommandHandler, ContextTypes

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = None  # type: ignore
    Application = None  # type: ignore
    CommandHandler = None  # type: ignore
    ContextTypes = None  # type: ignore
    Update = None  # type: ignore


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
HEALTH_FILE = PROJECT_ROOT / "ops" / "health" / "telegram_bot.json"


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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    persist_message_user(update)
    if update.message:
        await update.message.reply_text(get_start_message())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - shows commands not in /start, with role-based filtering."""
    if not update.message:
        return

    # Get user's role from database
    telegram_user_id = update.effective_user.id if update.effective_user else None
    is_admin = False

    if telegram_user_id:
        session = create_session()
        try:
            from execqueue.db.models import TelegramUser
            from sqlalchemy import select

            user = session.execute(
                select(TelegramUser).where(TelegramUser.telegram_id == telegram_user_id)
            ).scalar_one_or_none()
            is_admin = user is not None and user.role == "admin"
        except Exception:
            logger.exception("Failed to check user role for help command")
        finally:
            session.close()

    # Build help message with role-based commands
    help_message = (
        "📖 *ExecQueue Bot Help*\n\n"
        "Zusätzliche Befehle:\n"
    )

    # Add admin-only commands
    if is_admin:
        help_message += "/restart - System neu starten (Admin)\n"

    if not is_admin:
        help_message += "(Keine zusätzlichen Befehle für deine Rolle)\n"

    help_message += "\nFür weitere Informationen zur Nutzung besuchen Sie die Dokumentation."

    await update.message.reply_text(help_message)


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /health command."""
    if update.message:
        await update.message.reply_text(get_health_command_message())


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /restart command - Admin only.
    
    Triggers system restart via API endpoint.
    """
    if not update.message:
        return

    # Check if user is admin
    telegram_user_id = update.effective_user.id if update.effective_user else None
    is_admin = False

    if telegram_user_id:
        session = create_session()
        try:
            from execqueue.db.models import TelegramUser
            from sqlalchemy import select

            user = session.execute(
                select(TelegramUser).where(TelegramUser.telegram_id == telegram_user_id)
            ).scalar_one_or_none()
            is_admin = user is not None and user.role == "admin"
        except Exception:
            logger.exception("Failed to check user role for restart command")
        finally:
            session.close()

    if not is_admin:
        await update.message.reply_text(
            "❌ Zugriff verweigert. Dieser Befehl ist nur für Administratoren verfügbar."
        )
        return

    # Send confirmation that restart is in progress
    await update.message.reply_text(
        "🔄 *System-Neustart wird vorbereitet...*\n\n"
        "Sende Anfrage an API. Dies kann einen Moment dauern.",
        parse_mode="Markdown"
    )

    # Trigger restart via API (async, don't block)
    from execqueue.workers.telegram.commands import trigger_system_restart

    try:
        success, message = await trigger_system_restart()
        
        if success:
            await update.message.reply_text(
                f"✅ *Neustart erfolgreich ausgelöst*\n\n{message}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ *Neustart fehlgeschlagen*\n\n{message}",
                parse_mode="Markdown"
            )
    except Exception as exc:
        logger.exception("Error during restart command")
        await update.message.reply_text(
            f"❌ *Fehler beim Neustart*\n\nEin unerwarteter Fehler ist aufgetreten:\n{str(exc)}",
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

    return application


async def health_reporter(polling_timeout: int) -> None:
    """Periodically update the bot health file."""
    while True:
        try:
            write_health_status("ok", "Telegram bot is running and polling for updates.")
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
    write_health_status("starting", "Telegram bot is initializing...")

    application = create_bot_application(
        token=settings.telegram_bot_token,
        polling_timeout=settings.telegram_polling_timeout,
    )

    loop = asyncio.get_running_loop()

    def shutdown_handler() -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received, stopping bot...")
        write_health_status("not_ok", "Telegram bot is shutting down.")
        application.stop()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            signal.signal(sig, lambda sig, frame: shutdown_handler())

    await application.initialize()
    await application.start()

    logger.info("Bot started successfully. Press Ctrl+C to stop.")

    try:
        await send_startup_notification()
    except Exception:
        logger.exception("Failed to send startup notification, but bot continues running")

    health_task = asyncio.create_task(health_reporter(settings.telegram_polling_timeout))

    await application.updater.start_polling(
        timeout=settings.telegram_polling_timeout,
        allowed_updates=Update.ALL_TYPES,
    )

    await asyncio.Event().wait()

    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass

    write_health_status("not_ok", "Telegram bot stopped.")


def main() -> None:
    """Main entry point for the Telegram bot."""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        write_health_status("not_ok", "Telegram bot stopped by user.")
    except Exception as exc:
        logger.error("Bot error: %s", exc)
        write_health_status("not_ok", f"Bot error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
