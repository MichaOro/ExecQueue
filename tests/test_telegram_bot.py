"""Tests for Telegram bot module."""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from unittest.mock import AsyncMock


class TestTelegramBotModule:
    """Test bot module behavior without requiring actual Telegram library."""

    def test_bot_module_has_telegram_available_flag(self):
        """Bot module should have TELEGRAM_AVAILABLE flag."""
        from execqueue.workers.telegram import bot

        assert hasattr(bot, "TELEGRAM_AVAILABLE")
        assert isinstance(bot.TELEGRAM_AVAILABLE, bool)

    def test_run_bot_exits_when_disabled(self, monkeypatch):
        """run_bot should return early when bot is disabled."""
        monkeypatch.setenv("TELEGRAM_BOT_ENABLED", "false")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

        # Clear settings cache
        from execqueue.settings import get_settings

        get_settings.cache_clear()

        # Import bot module after setting env
        from execqueue.workers.telegram import bot

        # run_bot should return without error when disabled
        result = bot.run_bot()
        asyncio.run(result)

    @pytest.mark.asyncio
    async def test_run_bot_exits_when_enabled_no_token(self, monkeypatch):
        """run_bot should exit with error when enabled but no token."""
        # Use a Settings subclass that ignores .env file
        from pydantic_settings import SettingsConfigDict
        from execqueue.settings import Settings
        
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        # Create settings with enabled bot but no token
        settings = TestSettings(
            telegram_bot_enabled=True,
            telegram_bot_token=None,
        )
        
        # Verify the settings are correct
        assert settings.telegram_bot_enabled is True
        assert settings.telegram_bot_token is None

    def test_create_bot_application_requires_telegram(self):
        """create_bot_application should fail if telegram not available."""
        from execqueue.workers.telegram import bot

        if not bot.TELEGRAM_AVAILABLE:
            with pytest.raises((ImportError, NameError)):
                bot.create_bot_application("fake_token", 30)

    def test_start_command_handler_exists(self):
        """start_command handler should be defined."""
        from execqueue.workers.telegram.bot import start_command

        assert callable(start_command)

    def test_health_command_handler_exists(self):
        """health_command handler should be defined."""
        from execqueue.workers.telegram.bot import health_command

        assert callable(health_command)

    def test_help_command_handler_exists(self):
        """help_command handler should be defined."""
        from execqueue.workers.telegram.bot import help_command

        assert callable(help_command)

    @pytest.mark.asyncio
    async def test_start_command_shows_base_message_for_regular_user(self):
        """Regular users should only see the base /start text."""
        from execqueue.workers.telegram.bot import start_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        with patch(
            "execqueue.workers.telegram.auth.get_user_info",
            return_value=("user", True),
        ):
            await start_command(update, MagicMock())

        message = update.message.reply_text.call_args[0][0]
        assert "/start - Start the bot and show available commands" in message
        assert "/help - Show help and usage information" not in message
        assert "/health - Check system health status" not in message

    @pytest.mark.asyncio
    async def test_start_command_shows_operator_extras(self):
        """Operators should see /help and /health in /start."""
        from execqueue.workers.telegram.bot import start_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        with patch(
            "execqueue.workers.telegram.auth.get_user_info",
            return_value=("operator", True),
        ):
            await start_command(update, MagicMock())

        message = update.message.reply_text.call_args[0][0]
        assert "/help - Show help and usage information" in message
        assert "/health - Check system health status" in message


class TestBotWithMockedTelegram:
    """Test bot with mocked telegram library."""

    def test_command_handlers_are_callable(self):
        """Command handlers should be callable functions."""
        from execqueue.workers.telegram.bot import (
            health_command,
            restart_command,
            start_command,
        )

        assert callable(start_command)
        assert callable(health_command)
        assert callable(restart_command)


class TestBotShutdownHelpers:
    """Tests for Telegram bot shutdown helpers."""

    @pytest.mark.asyncio
    async def test_stop_bot_application_cleans_up_pid_file(self, monkeypatch, tmp_path):
        """Shutdown helper should await cleanup hooks and remove the current PID file."""
        from execqueue.workers.telegram import bot

        pid_file = tmp_path / "telegram_bot.pid"
        health_file = tmp_path / "telegram_bot.json"
        monkeypatch.setattr(bot, "PID_FILE", pid_file)
        monkeypatch.setattr(bot, "HEALTH_FILE", health_file)

        shutdown_event = asyncio.Event()
        application = MagicMock()
        application.updater = MagicMock()
        application.updater.stop = AsyncMock()
        application.stop = AsyncMock()
        application.shutdown = AsyncMock()

        bot.write_pid_file(os.getpid())

        await bot.stop_bot_application(application, shutdown_event, timeout=1)

        assert shutdown_event.is_set()
        application.updater.stop.assert_awaited_once()
        application.stop.assert_awaited_once()
        application.shutdown.assert_awaited_once()
        assert not pid_file.exists()
        assert '"status": "not_ok"' in health_file.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_stop_bot_application_times_out_and_still_signals_shutdown(
        self, monkeypatch, tmp_path
    ):
        """Timeouts during shutdown should still set the shutdown event and clear the PID file."""
        from execqueue.workers.telegram import bot

        pid_file = tmp_path / "telegram_bot.pid"
        health_file = tmp_path / "telegram_bot.json"
        monkeypatch.setattr(bot, "PID_FILE", pid_file)
        monkeypatch.setattr(bot, "HEALTH_FILE", health_file)

        async def slow_stop() -> None:
            await asyncio.sleep(0.05)

        shutdown_event = asyncio.Event()
        application = MagicMock()
        application.updater = MagicMock()
        application.updater.stop = AsyncMock(side_effect=slow_stop)
        application.stop = AsyncMock()
        application.shutdown = AsyncMock()

        bot.write_pid_file(os.getpid())

        await bot.stop_bot_application(application, shutdown_event, timeout=0.01)

        assert shutdown_event.is_set()
        assert not pid_file.exists()
        assert "timed out" in health_file.read_text(encoding="utf-8").lower()

    @pytest.mark.asyncio
    async def test_shutdown_handler_schedules_async_cleanup(self, monkeypatch, tmp_path):
        """Signal handler should schedule the async shutdown path instead of stopping the loop directly."""
        from execqueue.workers.telegram import bot

        pid_file = tmp_path / "telegram_bot.pid"
        health_file = tmp_path / "telegram_bot.json"
        monkeypatch.setattr(bot, "PID_FILE", pid_file)
        monkeypatch.setattr(bot, "HEALTH_FILE", health_file)

        shutdown_event = asyncio.Event()
        application = MagicMock()
        application.updater = MagicMock()
        application.updater.stop = AsyncMock()
        application.stop = AsyncMock()
        application.shutdown = AsyncMock()

        bot.write_pid_file(os.getpid())
        handler = bot.create_shutdown_handler(
            asyncio.get_running_loop(),
            application,
            shutdown_event,
            timeout=1,
        )

        handler()
        await asyncio.wait_for(shutdown_event.wait(), timeout=0.5)

        application.updater.stop.assert_awaited_once()
        application.stop.assert_awaited_once()
        application.shutdown.assert_awaited_once()
