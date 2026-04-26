"""Tests for Telegram notification user functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from execqueue.workers.telegram.bot import send_notification_to_user, send_notification_to_channel, TELEGRAM_AVAILABLE


@pytest.mark.skipif(not TELEGRAM_AVAILABLE, reason="python-telegram-bot not installed")
class TestSendNotificationToUser:
    """Tests for the send_notification_to_user function."""

    @pytest.mark.asyncio
    async def test_notification_user_not_configured(self):
        """Test that function returns False when user is not configured."""
        result = await send_notification_to_user(None, "Test message")
        assert result is False

    @pytest.mark.asyncio
    async def test_notification_sent_successfully(self):
        """Test that notification is sent successfully when user is configured."""
        with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.telegram_bot_token = "test_token"
            mock_get_settings.return_value = mock_settings

            with patch("execqueue.workers.telegram.bot.Bot") as mock_bot_class:
                mock_bot_instance = AsyncMock()
                mock_bot_instance.send_message = AsyncMock()
                mock_bot_class.return_value = mock_bot_instance

                result = await send_notification_to_user("123456789", "Test notification")

                assert result is True
                mock_bot_instance.send_message.assert_called_once()
                call_args = mock_bot_instance.send_message.call_args
                assert call_args[1]["chat_id"] == "123456789"
                assert call_args[1]["text"] == "Test notification"
                assert call_args[1]["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_notification_failure_logged(self):
        """Test that notification failure is logged and returns False."""
        with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.telegram_bot_token = "test_token"
            mock_get_settings.return_value = mock_settings

            with patch("execqueue.workers.telegram.bot.Bot") as mock_bot_class:
                mock_bot_instance = AsyncMock()
                mock_bot_instance.send_message = AsyncMock(side_effect=Exception("User not found"))
                mock_bot_class.return_value = mock_bot_instance

                with patch("execqueue.workers.telegram.bot.logger") as mock_logger:
                    result = await send_notification_to_user("123456789", "Test notification")

                    assert result is False
                    mock_logger.error.assert_called_once()
                    assert "Failed to send notification to user" in mock_logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_notification_with_special_characters(self):
        """Test that notification handles special Markdown characters."""
        with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.telegram_bot_token = "test_token"
            mock_get_settings.return_value = mock_settings

            with patch("execqueue.workers.telegram.bot.Bot") as mock_bot_class:
                mock_bot_instance = AsyncMock()
                mock_bot_instance.send_message = AsyncMock()
                mock_bot_class.return_value = mock_bot_instance

                message = "🟢 *Bot Online*\n\nTest mit **Bold** und _Italic_"
                result = await send_notification_to_user("123456789", message)

                assert result is True
                call_args = mock_bot_instance.send_message.call_args
                assert call_args[1]["text"] == message


class TestSendNotificationToChannel:
    """Tests for send_notification_to_channel wrapper function."""

    @pytest.mark.asyncio
    async def test_wraps_send_notification_to_user(self):
        """Test that send_notification_to_channel uses telegram_notification_user_id."""
        with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.telegram_notification_user_id = "987654321"
            mock_settings.telegram_bot_token = "test_token"
            mock_get_settings.return_value = mock_settings

            with patch("execqueue.workers.telegram.bot.send_notification_to_user") as mock_send:
                mock_send.return_value = True

                result = await send_notification_to_channel("Test message")

                assert result is True
                mock_send.assert_called_once_with("987654321", "Test message")

    @pytest.mark.asyncio
    async def test_returns_false_when_no_notification_user(self):
        """Test that function returns False when notification user is not configured."""
        with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.telegram_notification_user_id = None
            mock_settings.telegram_bot_token = "test_token"
            mock_get_settings.return_value = mock_settings

            result = await send_notification_to_channel("Test message")
            assert result is False


class TestSendNotificationToUserNoTelegram:
    """Tests for send_notification_to_user when telegram is not available."""

    @pytest.mark.asyncio
    async def test_returns_false_when_telegram_not_installed(self):
        """Test that function returns False when telegram library is not available."""
        with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.telegram_bot_token = "test_token"
            mock_get_settings.return_value = mock_settings

            with patch("execqueue.workers.telegram.bot.TELEGRAM_AVAILABLE", False):
                with patch("execqueue.workers.telegram.bot.logger") as mock_logger:
                    result = await send_notification_to_user("123456789", "Test message")

                    assert result is False
                    mock_logger.error.assert_called_once()
                    assert "python-telegram-bot not installed" in mock_logger.error.call_args[0][0]
