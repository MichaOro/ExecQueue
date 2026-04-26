"""Telegram bot self-health reporting."""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from execqueue.settings import get_settings
from execqueue.workers.telegram.commands import (
    get_health_command_message,
    get_restart_command_message,
    get_start_message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import telegram bot library lazily
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


# Health file path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
HEALTH_FILE = PROJECT_ROOT / "ops" / "health" / "telegram_bot.json"


def write_health_status(status: str, detail: str = "", include_pid: bool = False) -> None:
    """Write bot health status to file for API to read.
    
    Args:
        status: Health status ("ok", "not_ok", "starting", "maintenance", etc.)
        detail: Human-readable detail message
        include_pid: If True, include PID for debugging (default: False)
    """
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    health_data = {
        "component": "telegram_bot",
        "status": status,
        "detail": detail,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }
    
    # PID is optional, only include if explicitly requested
    if include_pid:
        health_data["pid"] = os.getpid()
    
    try:
        HEALTH_FILE.write_text(json.dumps(health_data, indent=2))
        logger.debug(f"Health status written: {status}")
    except Exception as e:
        logger.error(f"Failed to write health status: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if update.message:
        await update.message.reply_text(get_start_message())


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /health command - returns bot's internal health."""
    if update.message:
        await update.message.reply_text(get_health_command_message())


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /restart command."""
    if update.message:
        await update.message.reply_text(get_restart_command_message())


def create_bot_application(token: str, polling_timeout: int) -> Application:
    """Create and configure the Telegram bot application."""
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("restart", restart_command))

    return application


async def health_reporter(polling_timeout: int) -> None:
    """Periodically write health status to file."""
    while True:
        try:
            write_health_status("ok", "Telegram bot is running and polling for updates.")
        except Exception as e:
            logger.error(f"Health reporter error: {e}")
        
        await asyncio.sleep(polling_timeout)  # Update health every polling cycle


async def run_bot() -> None:
    """Run the Telegram bot with polling and health reporting."""
    settings = get_settings()

    if not settings.telegram_bot_enabled:
        logger.info("Telegram bot is disabled (TELEGRAM_BOT_ENABLED=false)")
        # Write disabled status
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

    # Write initial health status
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

    # Start health reporter task
    health_task = asyncio.create_task(
        health_reporter(settings.telegram_polling_timeout)
    )

    await application.updater.start_polling(
        timeout=settings.telegram_polling_timeout,
        allowed_updates=Update.ALL_TYPES,
    )

    # Wait for stop signal
    await asyncio.Event().wait()

    # Cancel health reporter
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
    except Exception as e:
        logger.error(f"Bot error: {e}")
        write_health_status("not_ok", f"Bot error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
