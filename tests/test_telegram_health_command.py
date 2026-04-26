"""Tests for Telegram health command functionality."""

import pytest
from unittest.mock import MagicMock, patch

from execqueue.workers.telegram.commands import (
    get_health_command_message,
    _get_status_emoji,
    get_command_list,
)


class TestGetStatusEmoji:
    """Tests for the _get_status_emoji helper function."""

    def test_ok_status_returns_green_circle(self):
        """Test that 'ok' status returns green circle emoji."""
        assert _get_status_emoji("ok") == "🟢"

    def test_degraded_status_returns_yellow_circle(self):
        """Test that 'degraded' status returns yellow circle emoji."""
        assert _get_status_emoji("degraded") == "🟡"

    def test_not_ok_status_returns_red_circle(self):
        """Test that 'not_ok' status returns red circle emoji."""
        assert _get_status_emoji("not_ok") == "🔴"

    def test_unknown_status_returns_white_circle(self):
        """Test that unknown status returns white circle emoji."""
        assert _get_status_emoji("unknown") == "⚪"


class TestHealthCommandMessage:
    """Tests for the get_health_command_message function."""

    def test_health_message_shows_overall_status_ok(self):
        """Test that health message shows overall OK status."""
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="ok",
                checks={
                    "api": MagicMock(status="ok", detail="API is running"),
                    "database": MagicMock(status="ok", detail="Database connected"),
                    "telegram_bot": MagicMock(status="ok", detail="Bot is polling"),
                }
            )

            message = get_health_command_message()

            assert "🏥 *System Health Report*" in message
            assert "Overall Status: 🟢 *OK*" in message
            assert "🟢 *Api*" in message
            assert "🟢 *Database*" in message
            assert "🟢 *Telegram Bot*" in message

    def test_health_message_shows_degraded_status(self):
        """Test that health message shows degraded status."""
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="degraded",
                checks={
                    "api": MagicMock(status="ok", detail="API is running"),
                    "database": MagicMock(status="degraded", detail="Slow connection"),
                }
            )

            message = get_health_command_message()

            assert "Overall Status: 🟡 *Degraded*" in message
            assert "🟡 *Database*" in message
            assert "   Status: Degraded" in message

    def test_health_message_shows_error_status(self):
        """Test that health message shows error status."""
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="not_ok",
                checks={
                    "api": MagicMock(status="not_ok", detail="API not responding"),
                }
            )

            message = get_health_command_message()

            assert "Overall Status: 🔴 *Error*" in message
            assert "🔴 *Api*" in message
            assert "   Status: Error" in message

    def test_health_message_lists_all_components(self):
        """Test that health message lists all registered components."""
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="ok",
                checks={
                    "api": MagicMock(status="ok", detail="API healthy"),
                    "database": MagicMock(status="ok", detail="DB connected"),
                    "telegram_bot": MagicMock(status="ok", detail="Bot running"),
                }
            )

            message = get_health_command_message()

            # Check all components are listed (with proper formatting)
            assert "*Api*" in message
            assert "*Database*" in message
            assert "*Telegram Bot*" in message  # Underscore should be replaced with space

            # Check details are shown
            assert "API healthy" in message
            assert "DB connected" in message
            assert "Bot running" in message

    def test_health_message_format_with_separators(self):
        """Test that health message has proper formatting with separators."""
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="ok",
                checks={
                    "api": MagicMock(status="ok", detail="OK"),
                }
            )

            message = get_health_command_message()

            assert "─" in message  # Separator lines
            assert "*Component Status:*" in message

    def test_health_message_handles_exceptions(self):
        """Test that health message handles exceptions gracefully."""
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.side_effect = Exception("Test error")

            message = get_health_command_message()

            assert "❌ *Health Check Error*" in message
            assert "Unable to retrieve health status" in message
            assert "Test error" in message


class TestCommandList:
    """Tests for the command list."""

    def test_health_command_in_list(self):
        """Test that health command is in the command list."""
        commands = get_command_list()
        health_cmd = next((cmd for cmd in commands if cmd["command"] == "health"), None)
        
        assert health_cmd is not None
        assert health_cmd["description"] == "Check system health status"
