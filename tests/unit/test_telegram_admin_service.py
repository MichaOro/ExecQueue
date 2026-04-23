"""
Unit-Tests für Telegram Admin Service.
"""

import pytest
from unittest.mock import MagicMock, patch

from execqueue.services.telegram_admin_service import TelegramAdminService, log_admin_action
from execqueue.models.telegram_user import TelegramUser


@pytest.fixture
def sample_admin_user():
    """Erstellt einen Test-Admin-Benutzer."""
    return TelegramUser(
        telegram_id="123456789",
        username="test_admin",
        role="admin",
        is_test=True
    )


@pytest.fixture
def sample_operator_user():
    """Erstellt einen Test-Operator-Benutzer."""
    return TelegramUser(
        telegram_id="987654321",
        username="test_operator",
        role="operator",
        is_test=True
    )


@pytest.fixture
def sample_observer_user():
    """Erstellt einen Test-Observer-Benutzer."""
    return TelegramUser(
        telegram_id="555555555",
        username="test_observer",
        role="observer",
        is_test=True
    )


class TestTelegramAdminService:
    """Unit-Tests für Admin-Service."""

    def test_list_all_users_returns_all(self, sample_admin_user, sample_operator_user):
        """Testet dass alle Benutzer gelistet werden."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.all.return_value = [sample_admin_user, sample_operator_user]
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            users = service.list_all_users()
            
            assert len(users) == 2

    def test_get_user_by_telegram_id(self, sample_admin_user):
        """Testet Benutzer-Ermittlung nach Telegram-ID."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = sample_admin_user
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            user = service.get_user_by_telegram_id("123456789")
            
            assert user is not None
            assert user.telegram_id == "123456789"
            assert user.role == "admin"

    def test_grant_admin_role_creates_new_user(self):
        """Testet dass grant_admin_role neuen Benutzer erstellt."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = None  # User nicht gefunden
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            user = service.grant_admin_role("999999999")
            
            assert user.role == "admin"
            assert user.telegram_id == "999999999"

    def test_grant_admin_role_updates_existing_user(self, sample_operator_user):
        """Testet dass grant_admin_role Rolle aktualisiert."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = sample_operator_user
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            user = service.grant_admin_role("987654321")
            
            assert user.role == "admin"

    def test_revoke_admin_role_success(self, sample_admin_user):
        """Testet dass revoke_admin_role erfolgreich ist."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = sample_admin_user
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            result = service.revoke_admin_role("123456789")
            
            assert result is True
            assert sample_admin_user.role == "operator"

    def test_revoke_admin_role_fails_for_non_admin(self, sample_operator_user):
        """Testet dass revoke_admin_role False zurückgibt wenn kein Admin."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = sample_operator_user
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            result = service.revoke_admin_role("987654321")
            
            assert result is False

    def test_revoke_admin_role_fails_for_nonexistent_user(self):
        """Testet dass revoke_admin_role False zurückgibt wenn Benutzer nicht existiert."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            mock_sess.exec.return_value.first.return_value = None
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            result = service.revoke_admin_role("999999999")
            
            assert result is False

    def test_get_system_stats_returns_correct_counts(
        self, sample_admin_user, sample_operator_user, sample_observer_user
    ):
        """Testet dass System-Stats korrekt gezählt werden."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            
            # Mock für differente Queries - one() gibt int zurueck, nicht list
            mock_sess.exec.return_value.one.side_effect = [10, 5, 3, 1]
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            stats = service.get_system_stats()
            
            assert stats["tasks"] == 10
            assert stats["requirements"] == 5
            assert stats["telegram_users"] == 3
            assert stats["admin_users"] == 1

    def test_get_user_stats(self):
        """Testet Benutzer-Statistiken nach Rolle."""
        with patch('execqueue.services.telegram_admin_service.get_session') as mock_session:
            mock_sess = MagicMock()
            mock_sess.__enter__ = MagicMock(return_value=mock_sess)
            mock_sess.__exit__ = MagicMock(return_value=False)
            
            query_results = [2, 3, 1]  # observer, operator, admin counts
            mock_sess.exec.return_value.one.side_effect = query_results
            mock_session.return_value = mock_sess
            
            service = TelegramAdminService()
            stats = service.get_user_stats()
            
            assert stats["observers"] == 2
            assert stats["operators"] == 3
            assert stats["admins"] == 1

    def test_format_user_list_empty(self):
        """Testet Formatierung bei leerer Benutzer-Liste."""
        service = TelegramAdminService()
        result = service.format_user_list([])
        assert "Keine Benutzer" in result

    def test_format_user_list_with_users(
        self, sample_admin_user, sample_operator_user, sample_observer_user
    ):
        """Testet Formatierung mit Benutzern."""
        service = TelegramAdminService()
        users = [sample_admin_user, sample_operator_user, sample_observer_user]
        result = service.format_user_list(users)
        
        assert "test_admin" in result
        assert "test_operator" in result
        assert "test_observer" in result
        assert "admin" in result
        assert "operator" in result
        assert "observer" in result

    def test_format_stats(self):
        """Testet Formatierung von Statistiken."""
        with patch.object(TelegramAdminService, 'get_user_stats', return_value={"observers": 1, "operators": 1, "admins": 1}):
            service = TelegramAdminService()
            stats = {
                "tasks": 10,
                "requirements": 5,
                "telegram_users": 3,
                "admin_users": 1
            }
            result = service.format_stats(stats)
            
            assert "10" in result
            assert "5" in result
            assert "3" in result


class TestLogAdminAction:
    """Unit-Tests für Audit-Logging."""

    def test_log_admin_action_success(self, caplog):
        """Testet dass erfolgreiche Admin-Aktion geloggt wird."""
        with caplog.at_level("WARNING"):
            log_admin_action("123456789", "grant_admin", "987654321", True)
            
            assert "AUDIT" in caplog.text
            assert "123456789" in caplog.text
            assert "grant_admin" in caplog.text
            assert "987654321" in caplog.text

    def test_log_admin_action_failure(self, caplog):
        """Testet dass fehlgeschlagene Admin-Aktion geloggt wird."""
        with caplog.at_level("WARNING"):
            log_admin_action("123456789", "revoke_admin", "987654321", False)
            
            assert "AUDIT" in caplog.text
            assert "FAILED" in caplog.text
