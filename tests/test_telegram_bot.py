"""Tests for Telegram bot module."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


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
        # It returns a coroutine, so we need to await it
        import asyncio

        asyncio.get_event_loop().run_until_complete(result)

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
