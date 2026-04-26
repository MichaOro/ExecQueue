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
                    "api": MagicMock(component="api", status="OK", detail="API is running"),
                    "database": MagicMock(component="database", status="OK", detail="Database connected"),
                    "telegram_bot": MagicMock(component="telegram_bot", status="OK", detail="Bot is polling"),
                },
            )

            message = get_health_command_message()

            assert message.startswith("🟢 *System Health*")
            assert "🟢 API — OK" in message
            assert "🟢 Database — OK" in message
            assert "🟢 Telegram Bot — OK" in message

    def test_health_message_shows_degraded_status(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="DEGRADED",
                checks={
                    "api": MagicMock(component="api", status="OK", detail="API is running"),
                    "database": MagicMock(component="database", status="DEGRADED", detail="Slow connection"),
                },
            )

            message = get_health_command_message()

            assert message.startswith("🟡 *System Health*")
            assert "🟡 Database — Degraded" in message

    def test_health_message_shows_error_status(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="ERROR",
                checks={
                    "api": MagicMock(component="api", status="ERROR", detail="API not responding"),
                },
            )

            message = get_health_command_message()

            assert message.startswith("🔴 *System Health*")
            assert "🔴 API — Error" in message

    def test_health_message_lists_all_components(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="OK",
                checks={
                    "api": MagicMock(component="api", status="OK", detail="API healthy"),
                    "database": MagicMock(component="database", status="OK", detail="DB connected"),
                    "telegram_bot": MagicMock(component="telegram_bot", status="OK", detail="Bot running"),
                },
            )

            message = get_health_command_message()

            assert "API — OK" in message
            assert "Database — OK" in message
            assert "Telegram Bot — OK" in message

    def test_health_message_format_with_separators(self):
        with patch("execqueue.workers.telegram.commands.get_overall_health") as mock_health:
            mock_health.return_value = MagicMock(
                status="OK",
                checks={
                    "api": MagicMock(component="api", status="OK", detail="OK"),
                },
            )

            message = get_health_command_message()

            assert "━━━━━━━━━━━━━━━━━━━━" in message

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
