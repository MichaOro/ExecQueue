"""Telegram bot with polling and command handling."""

import asyncio
import logging
import signal
import sys

from execqueue.settings import get_settings
from execqueue.workers.telegram.commands import (
    get_health_command_message,
    get_restart_command_message,
    get_start_message,
)

# Type hints for telegram module
Bot: type

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import telegram bot library lazily to avoid hard dependency when bot is disabled
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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command.

    Args:
        update: The update object from Telegram.
        context: The context object from telegram.ext.
    """
    if update.message:
        await update.message.reply_text(get_start_message())


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /health command (placeholder).

    Args:
        update: The update object from Telegram.
        context: The context object from telegram.ext.
    """
    if update.message:
        await update.message.reply_text(get_health_command_message())


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /restart command (placeholder).

    Args:
        update: The update object from Telegram.
        context: The context object from telegram.ext.
    """
    if update.message:
        await update.message.reply_text(get_restart_command_message())


def create_bot_application(token: str, polling_timeout: int) -> Application:
    """Create and configure the Telegram bot application.

    Args:
        token: Telegram bot token.
        polling_timeout: Timeout for polling in seconds.

    Returns:
        Configured Application instance.
    """
    application = Application.builder().token(token).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("restart", restart_command))

    return application


async def run_bot() -> None:
    """Run the Telegram bot with polling.

    This function:
    1. Loads settings from environment
    2. Validates bot is enabled and has a token
    3. Creates the bot application
    4. Registers signal handlers for graceful shutdown
    5. Starts polling for updates
    """
    settings = get_settings()

    # Check if bot is enabled
    if not settings.telegram_bot_enabled:
        logger.info("Telegram bot is disabled (TELEGRAM_BOT_ENABLED=false)")
        return

    # Check if token is provided
    if not settings.telegram_bot_token:
        logger.error(
            "Telegram bot is enabled but TELEGRAM_BOT_TOKEN is not set. "
            "Please configure the bot token in your environment."
        )
        sys.exit(1)

    # Check if telegram library is available
    if not TELEGRAM_AVAILABLE:
        logger.error(
            "python-telegram-bot is not installed. "
            "Please install it with: pip install python-telegram-bot"
        )
        sys.exit(1)

    logger.info("Starting Telegram bot with polling...")

    # Create bot application
    application = create_bot_application(
        token=settings.telegram_bot_token,
        polling_timeout=settings.telegram_polling_timeout,
    )

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def shutdown_handler() -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received, stopping bot...")
        application.stop()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda sig, frame: shutdown_handler())

    # Start the bot
    await application.initialize()
    await application.start()

    logger.info("Bot started successfully. Press Ctrl+C to stop.")

    # Send startup notification if admin chat ID is configured
    if settings.telegram_admin_chat_id:
        try:
            bot: Bot = application.bot
            await bot.send_message(
                chat_id=settings.telegram_admin_chat_id,
                text=get_start_message(),
            )
            logger.info("Startup notification sent to admin chat.")
        except Exception as e:
            logger.warning(f"Failed to send startup notification: {e}")

    # Keep running until stopped
    await application.updater.start_polling(
        timeout=settings.telegram_polling_timeout,
        allowed_updates=Update.ALL_TYPES,
    )

    # Wait for stop signal
    await asyncio.Event().wait()


def main() -> None:
    """Main entry point for the Telegram bot."""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
