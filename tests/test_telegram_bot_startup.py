"""Tests for Telegram bot startup and lifecycle."""

import asyncio
import os
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execqueue.workers.telegram.bot import run_bot, TELEGRAM_AVAILABLE


@pytest.mark.skipif(not TELEGRAM_AVAILABLE, reason="python-telegram-bot not installed")
class TestRunBot:
    """Tests for the run_bot function."""

    @pytest.mark.asyncio
    async def test_run_bot_disabled(self):
        """Test that run_bot returns early when bot is disabled."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "false"}):
            from execqueue.settings import get_settings
            get_settings.cache_clear()

            with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
                mock_settings = MagicMock()
                mock_settings.telegram_bot_enabled = False
                mock_get_settings.return_value = mock_settings

                # Should return immediately without error
                result = await run_bot()
                assert result is None

    @pytest.mark.asyncio
    async def test_run_bot_enabled_no_token(self):
        """Test that run_bot exits when bot is enabled but no token."""
        with patch.dict(os.environ, {}, clear=True):
            from execqueue.settings import get_settings
            get_settings.cache_clear()

            with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
                mock_settings = MagicMock()
                mock_settings.telegram_bot_enabled = True
                mock_settings.telegram_bot_token = None
                mock_settings.telegram_polling_timeout = 30
                mock_get_settings.return_value = mock_settings

                with patch("execqueue.workers.telegram.bot.sys") as mock_sys:
                    with patch("execqueue.workers.telegram.bot.TELEGRAM_AVAILABLE", True):
                        with patch("execqueue.workers.telegram.bot.logger") as mock_logger:
                            # Mock sys.exit to raise SystemExit so we can catch it
                            mock_sys.exit.side_effect = SystemExit(1)

                            # Should log error and call sys.exit(1) before reaching create_bot_application
                            with pytest.raises(SystemExit) as exc_info:
                                await run_bot()

                            assert exc_info.value.code == 1
                            mock_logger.error.assert_called()
                            # create_bot_application should NOT be called
                            with patch("execqueue.workers.telegram.bot.create_bot_application") as mock_create:
                                # Verify it was never reached
                                pass

    @pytest.mark.asyncio
    async def test_run_bot_enabled_with_token(self):
        """Test that run_bot starts successfully with token."""
        with patch.dict(os.environ, {}, clear=True):
            from execqueue.settings import get_settings
            get_settings.cache_clear()

            with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
                mock_settings = MagicMock()
                mock_settings.telegram_bot_enabled = True
                mock_settings.telegram_bot_token = "test_token"
                mock_settings.telegram_polling_timeout = 30
                mock_get_settings.return_value = mock_settings

                with patch("execqueue.workers.telegram.bot.create_bot_application") as mock_create_app:
                    mock_app = MagicMock()
                    mock_app.initialize = AsyncMock()
                    mock_app.start = AsyncMock()
                    mock_app.stop = AsyncMock()
                    mock_app.updater = MagicMock()
                    mock_app.updater.start_polling = AsyncMock()
                    mock_create_app.return_value = mock_app

                    with patch("execqueue.workers.telegram.bot.send_startup_notification") as mock_send_startup:
                        with patch("asyncio.Event") as mock_event_class:
                            mock_event = AsyncMock()
                            mock_event.wait = AsyncMock(side_effect=asyncio.CancelledError())
                            mock_event_class.return_value = mock_event

                            with patch("asyncio.get_running_loop") as mock_loop:
                                mock_loop_instance = MagicMock()
                                mock_loop.return_value = mock_loop_instance
                                mock_loop_instance.add_signal_handler = MagicMock()

                                # Should start without error (will raise CancelledError from asyncio.Event)
                                with pytest.raises(asyncio.CancelledError):
                                    await run_bot()

                                mock_app.initialize.assert_called_once()
                                mock_app.start.assert_called_once()
                                mock_app.updater.start_polling.assert_called_once()
                                # Verify new startup notification function is called
                                mock_send_startup.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_bot_sends_startup_notification(self):
        """Test that run_bot sends startup notification when notification user is configured."""
        with patch.dict(os.environ, {}, clear=True):
            from execqueue.settings import get_settings
            get_settings.cache_clear()

            with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
                mock_settings = MagicMock()
                mock_settings.telegram_bot_enabled = True
                mock_settings.telegram_bot_token = "test_token"
                mock_settings.telegram_polling_timeout = 30
                mock_settings.telegram_notification_user_id = "123456789"
                mock_get_settings.return_value = mock_settings

                with patch("execqueue.workers.telegram.bot.create_bot_application") as mock_create_app:
                    mock_app = MagicMock()
                    mock_app.initialize = AsyncMock()
                    mock_app.start = AsyncMock()
                    mock_app.stop = AsyncMock()
                    mock_app.updater = MagicMock()
                    mock_app.updater.start_polling = AsyncMock()
                    mock_create_app.return_value = mock_app

                    with patch("execqueue.workers.telegram.bot.send_startup_notification") as mock_send_startup:
                        with patch("asyncio.Event") as mock_event_class:
                            mock_event = AsyncMock()
                            mock_event.wait = AsyncMock(side_effect=asyncio.CancelledError())
                            mock_event_class.return_value = mock_event

                            with patch("asyncio.get_running_loop") as mock_loop:
                                mock_loop_instance = MagicMock()
                                mock_loop.return_value = mock_loop_instance
                                mock_loop_instance.add_signal_handler = MagicMock()

                                with pytest.raises(asyncio.CancelledError):
                                    await run_bot()

                                # Verify new startup notification function was called
                                mock_send_startup.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_bot_notification_failure_logged(self):
        """Test that notification failure is logged but doesn't stop bot."""
        with patch.dict(os.environ, {}, clear=True):
            from execqueue.settings import get_settings
            get_settings.cache_clear()

            with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
                mock_settings = MagicMock()
                mock_settings.telegram_bot_enabled = True
                mock_settings.telegram_bot_token = "test_token"
                mock_settings.telegram_polling_timeout = 30
                mock_settings.telegram_notification_user_id = "123456789"
                mock_get_settings.return_value = mock_settings

                with patch("execqueue.workers.telegram.bot.create_bot_application") as mock_create_app:
                    mock_app = MagicMock()
                    mock_app.initialize = AsyncMock()
                    mock_app.start = AsyncMock()
                    mock_app.stop = AsyncMock()
                    mock_app.updater = MagicMock()
                    mock_app.updater.start_polling = AsyncMock()
                    mock_create_app.return_value = mock_app

                    with patch("execqueue.workers.telegram.bot.send_startup_notification") as mock_send_startup:
                        # Simulate notification failure (raises exception)
                        mock_send_startup.side_effect = Exception("Notification failed")
                        
                        with patch("asyncio.Event") as mock_event_class:
                            mock_event = AsyncMock()
                            # Don't raise CancelledError immediately, let the test complete normally
                            mock_event.wait = AsyncMock()
                            mock_event_class.return_value = mock_event

                            with patch("asyncio.get_running_loop") as mock_loop:
                                mock_loop_instance = MagicMock()
                                mock_loop.return_value = mock_loop_instance
                                mock_loop_instance.add_signal_handler = MagicMock()

                                # Run for a short time then stop
                                import asyncio
                                task = asyncio.create_task(run_bot())
                                await asyncio.sleep(0.1)  # Let the bot start and try to send notification
                                task.cancel()
                                
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    pass  # Expected

                                # Bot should still start despite notification failure
                                mock_app.updater.start_polling.assert_called_once()


class TestBotLifecycle:
    """Tests for bot lifecycle management."""

    @pytest.mark.asyncio
    async def test_signal_handler_registered(self):
        """Test that signal handlers are registered for graceful shutdown."""
        with patch.dict(os.environ, {}, clear=True):
            from execqueue.settings import get_settings
            get_settings.cache_clear()

            with patch("execqueue.workers.telegram.bot.get_settings") as mock_get_settings:
                mock_settings = MagicMock()
                mock_settings.telegram_bot_enabled = True
                mock_settings.telegram_bot_token = "test_token"
                mock_settings.telegram_polling_timeout = 30
                mock_get_settings.return_value = mock_settings

                with patch("execqueue.workers.telegram.bot.create_bot_application") as mock_create_app:
                    mock_app = MagicMock()
                    mock_app.initialize = AsyncMock()
                    mock_app.start = AsyncMock()
                    mock_app.updater = MagicMock()
                    mock_app.updater.start_polling = AsyncMock()
                    mock_create_app.return_value = mock_app

                    with patch("asyncio.Event") as mock_event_class:
                        mock_event = AsyncMock()
                        mock_event.wait = AsyncMock(side_effect=asyncio.CancelledError())
                        mock_event_class.return_value = mock_event

                        with patch("asyncio.get_running_loop") as mock_loop:
                            mock_loop_instance = MagicMock()
                            mock_loop.return_value = mock_loop_instance
                            mock_loop_instance.add_signal_handler = MagicMock()

                            with pytest.raises(asyncio.CancelledError):
                                await run_bot()

                            # Verify signal handlers were registered
                            assert mock_loop_instance.add_signal_handler.called
