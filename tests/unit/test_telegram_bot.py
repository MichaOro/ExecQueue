"""
Unit-Tests für Telegram-Bot Commands und Funktionen.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from execqueue.workers.telegram_bot import TelegramBotWorker, BotError
from execqueue.models.telegram_user import TelegramUser


@pytest.fixture
def mock_update():
    """Erstellt einen Mock für telegram.Update."""
    update = MagicMock()
    update.effective_user.id = 123456789
    update.effective_user.username = "test_user"
    update.effective_user.first_name = "Test"
    update.effective_user.last_name = "User"
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Erstellt einen Mock für ContextTypes."""
    return MagicMock()
    context.args = []
    return context


@pytest.fixture
def sample_task():
    """Erstellt Beispiel-Task-Daten."""
    return {
        "id": 123,
        "title": "Test Task",
        "status": "queued",
        "execution_order": 1,
        "retry_count": 0,
        "max_retries": 5,
        "created_at": "2026-04-23T12:00:00Z",
        "last_result": None
    }


@pytest.fixture
def sample_tasks():
    """Erstellt Beispiel-Task-Liste."""
    return [
        {
            "id": 123,
            "title": "Test Task 1",
            "status": "queued",
            "execution_order": 1,
            "retry_count": 0,
            "max_retries": 5,
            "created_at": "2026-04-23T12:00:00Z"
        },
        {
            "id": 124,
            "title": "Test Task 2",
            "status": "in_progress",
            "execution_order": 2,
            "retry_count": 1,
            "max_retries": 5,
            "created_at": "2026-04-23T12:05:00Z"
        }
    ]


@pytest.fixture
def telegram_admin_user():
    """Erstellt einen Test-Admin-Benutzer."""
    return TelegramUser(
        telegram_id="123456789",
        username="test_admin",
        role="admin",
        is_test=True
    )


@pytest.fixture
def telegram_operator_user():
    """Erstellt einen Test-Operator-Benutzer."""
    return TelegramUser(
        telegram_id="987654321",
        username="test_operator",
        role="operator",
        is_test=True
    )


@pytest.fixture
def telegram_observer_user():
    """Erstellt einen Test-Observer-Benutzer."""
    return TelegramUser(
        telegram_id="555555555",
        username="test_observer",
        role="observer",
        is_test=True
    )


class TestTelegramBotCommands:
    """Unit-Tests für Telegram-Bot Commands."""

    @pytest.mark.asyncio
    async def test_handle_start_shows_greeting(self, mock_update, mock_context):
        """Testet dass /start eine Begrüßungsnachricht sendet."""
        bot = TelegramBotWorker()
        
        with patch.object(bot, 'get_or_create_user', return_value=None):
            await bot.handle_start(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Willkommen" in call_args or "Willkommen" in call_args
        assert "/help" in call_args

    @pytest.mark.asyncio
    async def test_handle_help_shows_all_commands(self, mock_update, mock_context):
        """Testet dass /help alle Commands auflistet."""
        bot = TelegramBotWorker()
        
        with patch.object(bot, 'check_user_permission', return_value=False):
            await bot.handle_help(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "/start" in call_args
        assert "/queue" in call_args
        assert "/status" in call_args
        assert "/health" in call_args

    @pytest.mark.asyncio
    async def test_handle_help_shows_operator_commands_for_operator(self, mock_update, mock_context):
        """Testet dass Operator Commands für Operator angezeigt werden."""
        bot = TelegramBotWorker()
        
        # Mock permission check to return True for operator
        with patch.object(bot, 'check_user_permission', side_effect=lambda uid, role: role in ["operator", "admin"]):
            await bot.handle_help(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "/create" in call_args
        assert "/cancel" in call_args

    @pytest.mark.asyncio
    async def test_handle_help_shows_admin_commands_for_admin(self, mock_update, mock_context):
        """Testet dass Admin Commands für Admin angezeigt werden."""
        bot = TelegramBotWorker()
        
        # Mock permission check to return True for admin
        with patch.object(bot, 'check_user_permission', return_value=True):
            await bot.handle_help(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "/start_scheduler" in call_args
        assert "/stop_scheduler" in call_args

    @pytest.mark.asyncio
    async def test_handle_queue_shows_tasks(self, mock_update, mock_context, sample_tasks):
        """Testet dass /queue Tasks anzeigt."""
        bot = TelegramBotWorker()
        
        with patch.object(bot, 'check_rate_limit', return_value=True):
            with patch.object(bot, 'call_api', return_value=sample_tasks):
                await bot.handle_queue(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Task" in call_args or "queue" in call_args.lower()

    @pytest.mark.asyncio
    async def test_handle_queue_rate_limit_exceeded(self, mock_update, mock_context):
        """Testet dass /queue bei Rate-Limit abgelehnt wird."""
        bot = TelegramBotWorker()
        
        with patch.object(bot, 'check_rate_limit', return_value=False):
            await bot.handle_queue(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Rate-Limit" in call_args

    @pytest.mark.asyncio
    async def test_handle_status_requires_task_id(self, mock_update, mock_context):
        """Testet dass /status ohne task_id eine Fehlermeldung zeigt."""
        bot = TelegramBotWorker()
        mock_context.args = []  # Keine Argumente
        
        await bot.handle_status(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "task_id" in call_args.lower() or "Task-ID" in call_args

    @pytest.mark.asyncio
    async def test_handle_status_shows_task_details(self, mock_update, mock_context, sample_task):
        """Testet dass /status <task_id> Details anzeigt."""
        bot = TelegramBotWorker()
        mock_context.args = ["123"]
        
        with patch.object(bot, 'check_rate_limit', return_value=True):
            with patch.object(bot, 'call_api', return_value=sample_task):
                await bot.handle_status(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "123" in call_args
        assert "Test Task" in call_args

    @pytest.mark.asyncio
    async def test_handle_health_shows_system_status(self, mock_update, mock_context):
        """Testet dass /health System-Status anzeigt."""
        bot = TelegramBotWorker()
        mock_health_data = {
            "status": "ok",
            "database_connected": True,
            "scheduler": {"running": True, "active_workers": 2},
            "metrics": {"queued_tasks": 5, "running_tasks": 1, "completed_tasks": 10}
        }
        
        with patch.object(bot, 'check_rate_limit', return_value=True):
            with patch.object(bot, 'call_api', return_value=mock_health_data):
                await bot.handle_health(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "System-Status" in call_args or "status" in call_args.lower()
        assert "Database" in call_args or "database" in call_args.lower()

    @pytest.mark.asyncio
    async def test_format_task_list_empty(self):
        """Testet Formatierung bei leerer Task-Liste."""
        bot = TelegramBotWorker()
        result = bot.format_task_list([])
        assert "Keine Tasks" in result

    @pytest.mark.asyncio
    async def test_format_task_list_with_tasks(self, sample_tasks):
        """Testet Formatierung mit Tasks."""
        bot = TelegramBotWorker()
        result = bot.format_task_list(sample_tasks)
        assert "123" in result
        assert "124" in result
        assert "Test Task" in result

    @pytest.mark.asyncio
    async def test_format_task_detail(self, sample_task):
        """Testet Formatierung von Task-Detail."""
        bot = TelegramBotWorker()
        result = bot.format_task_detail(sample_task)
        assert "123" in result
        assert "Test Task" in result
        assert "queued" in result


class TestTelegramBotRateLimiting:
    """Unit-Tests für Rate-Limiting."""

    def test_check_rate_limit_allows_within_limit(self):
        """Testet dass Requests innerhalb des Limits erlaubt werden."""
        bot = TelegramBotWorker()
        user_id = "test_user"
        
        # Alle Requests sollten erlaubt werden (unter Limit)
        for _ in range(5):
            assert bot.check_rate_limit(user_id) is True

    def test_check_rate_limit_blocks_over_limit(self):
        """Testet dass Requests über dem Limit blockiert werden."""
        bot = TelegramBotWorker()
        bot.rate_limit_per_minute = 3
        user_id = "test_user"
        
        # Erste 3 Requests sollten erlaubt werden
        assert bot.check_rate_limit(user_id) is True
        assert bot.check_rate_limit(user_id) is True
        assert bot.check_rate_limit(user_id) is True
        
        # 4. Request sollte blockiert werden
        assert bot.check_rate_limit(user_id) is False


class TestTelegramBotPermissions:
    """Unit-Tests für Rollen- und Berechtigungsprüfung."""

    @pytest.mark.asyncio
    async def test_check_user_permission_observer_cannot_access_operator(self, telegram_observer_user):
        """Testet dass Observer keine Operator-Commands ausführen können."""
        bot = TelegramBotWorker()
        
        with patch('execqueue.workers.telegram_bot.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = telegram_observer_user
            mock_session.return_value = mock_sess
            
            result = await bot.check_user_permission(telegram_observer_user.telegram_id, "operator")
            assert result is False

    @pytest.mark.asyncio
    async def test_check_user_permission_operator_can_access_operator(self, telegram_operator_user):
        """Testet dass Operator Operator-Commands ausführen können."""
        bot = TelegramBotWorker()
        
        with patch('execqueue.workers.telegram_bot.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = telegram_operator_user
            mock_session.return_value = mock_sess
            
            result = await bot.check_user_permission(telegram_operator_user.telegram_id, "operator")
            assert result is True

    @pytest.mark.asyncio
    async def test_check_user_permission_admin_can_access_all(self, telegram_admin_user):
        """Testet dass Admin alle Commands ausführen kann."""
        bot = TelegramBotWorker()
        
        with patch('execqueue.workers.telegram_bot.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = telegram_admin_user
            mock_session.return_value = mock_sess
            
            # Admin sollte alle Rollen haben
            assert await bot.check_user_permission(telegram_admin_user.telegram_id, "observer") is True
            assert await bot.check_user_permission(telegram_admin_user.telegram_id, "operator") is True
            assert await bot.check_user_permission(telegram_admin_user.telegram_id, "admin") is True

    @pytest.mark.asyncio
    async def test_check_user_permission_unknown_user_denied(self):
        """Testet dass unbekannte Benutzer abgelehnt werden."""
        bot = TelegramBotWorker()
        
        with patch('execqueue.workers.telegram_bot.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = None
            mock_session.return_value = mock_sess
            
            result = await bot.check_user_permission("999999999", "observer")
            assert result is False


class TestTelegramBotErrorHandling:
    """Unit-Tests für Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_bot_error_exception(self):
        """Testet dass BotError Exception korrekt funktioniert."""
        with pytest.raises(BotError) as exc_info:
            raise BotError("Test error")
        
        assert str(exc_info.value) == "Test error"

    @pytest.mark.asyncio
    async def test_handle_create_api_error(self, mock_update, mock_context):
        """Testet Fehlerbehandlung bei API-Fehlern."""
        bot = TelegramBotWorker()
        mock_context.args = ["test prompt"]
        
        with patch.object(bot, 'check_user_permission', return_value=True):
            with patch.object(bot, 'check_rate_limit', return_value=True):
                with patch.object(bot, 'call_api', side_effect=BotError("API Error")):
                    await bot.handle_create(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Fehler" in call_args or "Error" in call_args
