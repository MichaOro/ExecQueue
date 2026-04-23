"""
Unit-Tests für Telegram Notification Service.
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from execqueue.workers.telegram_notification_service import TelegramNotificationService
from execqueue.models.telegram_user import TelegramUser
from execqueue.models.telegram_notification import TelegramNotification


@pytest.fixture
def mock_bot():
    """Erstellt einen Mock für telegram.Bot."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=None)
    return bot


@pytest.fixture
def telegram_subscribed_user():
    """Erstellt einen abonnierten Test-Benutzer."""
    return TelegramUser(
        telegram_id="123456789",
        username="test_user",
        role="observer",
        subscribed_events=json.dumps({"task_completed": True, "validation_failed": True}),
        is_active=True,
        is_test=True
    )


@pytest.fixture
def telegram_unsubscribed_user():
    """Erstellt einen nicht-abonnierten Test-Benutzer."""
    return TelegramUser(
        telegram_id="987654321",
        username="test_user2",
        role="observer",
        subscribed_events=json.dumps({}),
        is_active=True,
        is_test=True
    )


@pytest.fixture
def sample_task():
    """Erstellt Beispiel-Task-Daten."""
    return {
        "id": 123,
        "title": "Test Task",
        "status": "done",
        "validation_summary": "Tests bestanden",
        "retry_count": 0,
        "max_retries": 5
    }


class TestTelegramNotificationService:
    """Unit-Tests für Notification-Service."""

    @pytest.mark.asyncio
    async def test_send_notification_sends_to_subscribed_user(self, mock_bot, telegram_subscribed_user):
        """Testet dass Notifications an abonnierte Benutzer gesendet werden."""
        service = TelegramNotificationService(bot=mock_bot)
        
        with patch('execqueue.workers.telegram_notification_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = telegram_subscribed_user
            mock_session.return_value = mock_sess
            
            await service.send_notification(
                user_telegram_id="123456789",
                event_type="task_completed",
                message="Test notification",
                task_id=123
            )
            
            mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_skips_unsubscribed_user(self, mock_bot, telegram_unsubscribed_user):
        """Testet dass Notifications nicht an nicht-abonnierte Benutzer gesendet werden."""
        service = TelegramNotificationService(bot=mock_bot)
        
        with patch('execqueue.workers.telegram_notification_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = telegram_unsubscribed_user
            mock_session.return_value = mock_sess
            
            await service.send_notification(
                user_telegram_id="987654321",
                event_type="task_completed",
                message="Test notification",
                task_id=123
            )
            
            mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_task_completed_formats_message(self, mock_bot, sample_task):
        """Testet dass Task-Abschluss-Nachricht korrekt formatiert wird."""
        service = TelegramNotificationService(bot=mock_bot)
        
        # Mock _notify_subscribers direkt, um die DB-Logik zu umgehen
        with patch.object(service, '_notify_subscribers', new_callable=AsyncMock) as mock_notify:
            await service.notify_task_completed(sample_task)
            mock_notify.assert_called_once()
            call_args = mock_notify.call_args
            assert "task_completed" in str(call_args)

    @pytest.mark.asyncio
    async def test_notify_validation_failed(self, mock_bot):
        """Testet dass Validierungsfehler-Nachricht gesendet wird."""
        service = TelegramNotificationService(bot=mock_bot)
        
        task = {
            "id": 456,
            "title": "Failed Task",
            "status": "failed",
            "retry_count": 3,
            "max_retries": 5
        }
        
        # Mock _notify_subscribers direkt
        with patch.object(service, '_notify_subscribers', new_callable=AsyncMock) as mock_notify:
            await service.notify_validation_failed(task)
            mock_notify.assert_called_once()
            call_args = mock_notify.call_args
            assert "validation_failed" in str(call_args)

    @pytest.mark.asyncio
    async def test_notify_retry_exhausted_notifies_admins(self, mock_bot):
        """Testet dass erschöpftes Retry-Limit Admins alarmiert."""
        service = TelegramNotificationService(bot=mock_bot)
        
        task = {
            "id": 789,
            "title": "Exhausted Task",
            "status": "failed",
            "retry_count": 5,
            "max_retries": 5
        }
        
        # Mock _notify_admins direkt
        with patch.object(service, '_notify_admins', new_callable=AsyncMock) as mock_notify:
            await service.notify_retry_exhausted(task)
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_scheduler_started(self, mock_bot):
        """Testet dass Scheduler-Start-Nachricht gesendet wird."""
        service = TelegramNotificationService(bot=mock_bot)
        
        with patch.object(service, '_notify_admins', new_callable=AsyncMock) as mock_notify:
            await service.notify_scheduler_started()
            mock_notify.assert_called_once_with("scheduler_started", "▶️ *Scheduler gestartet*")

    @pytest.mark.asyncio
    async def test_notify_scheduler_stopped(self, mock_bot):
        """Testet dass Scheduler-Stop-Nachricht gesendet wird."""
        service = TelegramNotificationService(bot=mock_bot)
        
        with patch.object(service, '_notify_admins', new_callable=AsyncMock) as mock_notify:
            await service.notify_scheduler_stopped()
            mock_notify.assert_called_once_with("scheduler_stopped", "⏹️ *Scheduler gestoppt*")

    @pytest.mark.asyncio
    async def test_save_notification_to_database(self, mock_bot):
        """Testet dass Notifications in DB gespeichert werden."""
        service = TelegramNotificationService(bot=mock_bot)
        
        with patch('execqueue.workers.telegram_notification_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_session.return_value = mock_sess
            
            await service._save_notification(
                mock_sess,
                user_telegram_id="123456789",
                event_type="task_completed",
                message="Test notification",
                task_id=123
            )
            
            mock_sess.add.assert_called_once()
            mock_sess.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_admin_user_ids_from_env_and_db(self):
        """Testet dass Admin-IDs aus Environment und DB kombiniert werden."""
        service = TelegramNotificationService()
        
        with patch('execqueue.workers.telegram_notification_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.all.return_value = ["db_admin123"]
            mock_session.return_value = mock_sess
            
            with patch('os.getenv', return_value="env_admin456"):
                admin_ids = service._get_admin_user_ids()
                assert "db_admin123" in admin_ids
                assert "env_admin456" in admin_ids
