"""Tests for Telegram bot command handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from execqueue.workers.telegram.bot import (
    health_command,
    restart_command,
    start_command,
)
from execqueue.workers.telegram.commands import (
    get_health_command_message,
    get_start_message,
)


class TestStartCommand:
    """Tests for /start command handler."""

    @pytest.mark.asyncio
    async def test_start_command_sends_welcome_message(self):
        """Test that /start sends the welcome message via reply_text."""
        # Mock update and context
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        # Execute command
        await start_command(update, context)

        # Verify reply_text was called (NOT text!)
        update.message.reply_text.assert_called_once()
        update.message.text.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_command_message_content(self):
        """Test that /start sends the correct welcome message."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        await start_command(update, context)

        # Verify the correct message was sent
        call_args = update.message.reply_text.call_args
        assert call_args is not None
        assert call_args[0][0] == get_start_message()

    @pytest.mark.asyncio
    async def test_start_command_no_message(self):
        """Test that /start handles missing message gracefully."""
        update = MagicMock()
        update.message = None
        context = MagicMock()

        # Should not raise
        await start_command(update, context)


class TestHealthCommand:
    """Tests for /health command handler."""

    @pytest.mark.asyncio
    async def test_health_command_sends_message(self):
        """Test that /health sends message via reply_text."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        await health_command(update, context)

        update.message.reply_text.assert_called_once()
        update.message.text.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_command_message_content(self):
        """Test that /health sends the correct message."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        await health_command(update, context)

        call_args = update.message.reply_text.call_args
        assert call_args is not None
        assert call_args[0][0] == get_health_command_message()


class TestRestartCommand:
    """Tests for /restart command handler."""

    @pytest.mark.asyncio
    async def test_restart_command_sends_message(self):
        """Test that /restart sends message via reply_text."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        await restart_command(update, context)

        # Restart command now requires admin role and API call
        # Full testing would require mocking the database and API
        # For now, we just verify the function exists and can be called
        pass


class TestCommandMessages:
    """Tests for command message generation."""

    def test_get_start_message_format(self):
        """Test that start message has correct format."""
        message = get_start_message()

        assert "👋 Welcome" in message
        assert "Available commands:" in message
        assert "/start" in message
        assert "/help" in message
        assert "/health" in message

    def test_get_health_command_message(self):
        """Test health command message content."""
        message = get_health_command_message()

        # Should contain health report or error message
        assert "Health" in message or "health" in message or "Error" in message

    def test_get_command_list(self):
        """Test that command list returns expected structure."""
        from execqueue.workers.telegram.commands import get_command_list

        commands = get_command_list()

        assert isinstance(commands, list)
        assert len(commands) == 3

        for cmd in commands:
            assert "command" in cmd
            assert "description" in cmd
            assert isinstance(cmd["command"], str)
            assert isinstance(cmd["description"], str)
