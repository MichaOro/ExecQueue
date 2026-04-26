"""Tests for Telegram health command functionality."""

from unittest.mock import MagicMock, patch

from execqueue.workers.telegram.commands import (
    _get_status_emoji,
    get_command_list,
    get_health_command_message,
)


class TestGetStatusEmoji:
    """Tests for the _get_status_emoji helper function."""

    def test_ok_status_returns_green_circle(self):
        assert _get_status_emoji("OK") == "🟢"

    def test_degraded_status_returns_yellow_circle(self):
        assert _get_status_emoji("DEGRADED") == "🟡"

    def test_error_status_returns_red_circle(self):
        assert _get_status_emoji("ERROR") == "🔴"

    def test_unknown_status_returns_red_circle(self):
        assert _get_status_emoji("unknown") == "🔴"


class TestHealthCommandMessage:
    """Tests for the get_health_command_message function."""

    def test_health_message_shows_overall_status_ok(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="OK",
                checks={
                    "api": MagicMock(status="OK", detail="API is running"),
                    "database": MagicMock(status="OK", detail="Database connected"),
                    "telegram_bot": MagicMock(status="OK", detail="Bot is polling"),
                },
            )

            message = get_health_command_message()

            assert "🏥 *System Health Report*" in message
            assert "Overall Status: 🟢 *OK*" in message
            assert "🟢 *Api*" in message
            assert "🟢 *Database*" in message
            assert "🟢 *Telegram Bot*" in message

    def test_health_message_shows_degraded_status(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="DEGRADED",
                checks={
                    "api": MagicMock(status="OK", detail="API is running"),
                    "database": MagicMock(status="DEGRADED", detail="Slow connection"),
                },
            )

            message = get_health_command_message()

            assert "Overall Status: 🟡 *Degraded*" in message
            assert "🟡 *Database*" in message
            assert "   Status: Degraded" in message

    def test_health_message_shows_error_status(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="ERROR",
                checks={
                    "api": MagicMock(status="ERROR", detail="API not responding"),
                },
            )

            message = get_health_command_message()

            assert "Overall Status: 🔴 *Error*" in message
            assert "🔴 *Api*" in message
            assert "   Status: Error" in message

    def test_health_message_lists_all_components(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="OK",
                checks={
                    "api": MagicMock(status="OK", detail="API healthy"),
                    "database": MagicMock(status="OK", detail="DB connected"),
                    "telegram_bot": MagicMock(status="OK", detail="Bot running"),
                },
            )

            message = get_health_command_message()

            assert "*Api*" in message
            assert "*Database*" in message
            assert "*Telegram Bot*" in message
            assert "API healthy" in message
            assert "DB connected" in message
            assert "Bot running" in message

    def test_health_message_format_with_separators(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="OK",
                checks={
                    "api": MagicMock(status="OK", detail="OK"),
                },
            )

            message = get_health_command_message()

            assert "─" in message
            assert "*Component Status:*" in message

    def test_health_message_handles_exceptions(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.side_effect = Exception("Test error")

            message = get_health_command_message()

            assert "❌ *Health Check Error*" in message
            assert "Unable to retrieve health status" in message
            assert "Test error" in message


class TestCommandList:
    """Tests for the command list."""

    def test_health_command_in_list(self):
        commands = get_command_list()
        health_cmd = next((cmd for cmd in commands if cmd["command"] == "health"), None)

        assert health_cmd is not None
        assert health_cmd["description"] == "Check system health status"
