"""Tests for Telegram notification service."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from execqueue.db.base import Base
from execqueue.db.engine import build_engine
from execqueue.db.models import TelegramUser
from execqueue.db.session import build_session_factory
from execqueue.settings import RuntimeEnvironment, Settings
from sqlalchemy import select

from execqueue.db.models import TelegramUser as TelegramUserModel
from execqueue.workers.telegram.notifications import (
    SUBSCRIPTION_STARTUP,
    get_startup_notification_recipients,
    is_user_subscribed_to_startup,
    update_user_last_active,
)
from execqueue.workers.telegram.persistence import (
    subscribe_user_to_startup,
    unsubscribe_user_from_startup,
    upsert_telegram_user,
)


class RuntimeTestSettings(Settings):
    """Settings variant that ignores the local .env file during tests."""

    model_config = SettingsConfigDict(env_file="", extra="ignore")


def create_sqlite_session():
    """Create an in-memory SQLite session for testing."""
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.TEST,
        database_url_test="sqlite+pysqlite:///:memory:",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session = build_session_factory(engine)()
    return engine, session


class TestGetStartupNotificationRecipients:
    """Tests for get_startup_notification_recipients function."""

    def test_returns_empty_list_when_no_users(self):
        """Test that empty list is returned when no users exist."""
        engine, session = create_sqlite_session()
        try:
            recipients = get_startup_notification_recipients(session)
            assert recipients == []
        finally:
            session.close()
            engine.dispose()

    def test_returns_only_active_subscribed_users(self):
        """Test that only active and subscribed users are returned."""
        engine, session = create_sqlite_session()
        try:
            # Create inactive subscribed user
            inactive_user = TelegramUser(
                telegram_id=111,
                first_name="Inactive",
                is_active=False,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )
            session.add(inactive_user)

            # Create active unsubscribed user
            unsubscribed_user = TelegramUser(
                telegram_id=222,
                first_name="Unsubscribed",
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: False},
            )
            session.add(unsubscribed_user)

            # Create active subscribed user
            active_subscribed = TelegramUser(
                telegram_id=333,
                first_name="Active",
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )
            session.add(active_subscribed)

            # Create active user with empty subscriptions
            empty_subs = TelegramUser(
                telegram_id=444,
                first_name="Empty",
                is_active=True,
                subscribed_events={},
            )
            session.add(empty_subs)

            session.commit()

            recipients = get_startup_notification_recipients(session)

            assert recipients == [333]
        finally:
            session.close()
            engine.dispose()

    def test_returns_multiple_active_subscribed_users(self):
        """Test that multiple active subscribed users are all returned."""
        engine, session = create_sqlite_session()
        try:
            user1 = TelegramUser(
                telegram_id=111,
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )
            user2 = TelegramUser(
                telegram_id=222,
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )
            user3 = TelegramUser(
                telegram_id=333,
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )

            session.add_all([user1, user2, user3])
            session.commit()

            recipients = get_startup_notification_recipients(session)

            assert sorted(recipients) == [111, 222, 333]
        finally:
            session.close()
            engine.dispose()


class TestIsUserSubscribedToStartup:
    """Tests for is_user_subscribed_to_startup function."""

    def test_returns_false_for_nonexistent_user(self):
        """Test that False is returned for user that doesn't exist."""
        engine, session = create_sqlite_session()
        try:
            result = is_user_subscribed_to_startup(session, 999)
            assert result is False
        finally:
            session.close()
            engine.dispose()

    def test_returns_false_for_inactive_user(self):
        """Test that inactive user is not considered subscribed."""
        engine, session = create_sqlite_session()
        try:
            user = TelegramUser(
                telegram_id=111,
                is_active=False,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )
            session.add(user)
            session.commit()

            result = is_user_subscribed_to_startup(session, 111)
            assert result is False
        finally:
            session.close()
            engine.dispose()

    def test_returns_false_for_unsubscribed_user(self):
        """Test that unsubscribed user returns False."""
        engine, session = create_sqlite_session()
        try:
            user = TelegramUser(
                telegram_id=111,
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: False},
            )
            session.add(user)
            session.commit()

            result = is_user_subscribed_to_startup(session, 111)
            assert result is False
        finally:
            session.close()
            engine.dispose()

    def test_returns_true_for_active_subscribed_user(self):
        """Test that active subscribed user returns True."""
        engine, session = create_sqlite_session()
        try:
            user = TelegramUser(
                telegram_id=111,
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )
            session.add(user)
            session.commit()

            result = is_user_subscribed_to_startup(session, 111)
            assert result is True
        finally:
            session.close()
            engine.dispose()


class TestUpdateUserLastActive:
    """Tests for update_user_last_active function."""

    def test_updates_existing_user(self):
        """Test that last_active is updated for existing user."""
        engine, session = create_sqlite_session()
        try:
            user = TelegramUser(
                telegram_id=111,
                is_active=True,
            )
            session.add(user)
            session.commit()

            # Store original timestamp
            original_id = user.id

            update_user_last_active(session, 111)

            # Verify user still exists and has updated last_active
            updated_user = session.execute(
                select(TelegramUserModel).where(TelegramUserModel.telegram_id == 111)
            ).scalar_one()

            assert updated_user.id == original_id  # id matches
            assert updated_user.last_active is not None
        finally:
            session.close()
            engine.dispose()

    def test_silently_ignores_nonexistent_user(self):
        """Test that nonexistent user doesn't cause error."""
        engine, session = create_sqlite_session()
        try:
            # Should not raise
            update_user_last_active(session, 999)
        finally:
            session.close()
            engine.dispose()


class TestSubscribeUserToStartup:
    """Tests for subscribe_user_to_startup function."""

    def test_subscribes_existing_user(self):
        """Test that existing user can be subscribed."""
        engine, session = create_sqlite_session()
        try:
            user = TelegramUser(
                telegram_id=111,
                is_active=True,
                subscribed_events={},
            )
            session.add(user)
            session.commit()

            result = subscribe_user_to_startup(session, 111)

            assert result is True

            updated = session.execute(
                select(TelegramUserModel).where(TelegramUserModel.telegram_id == 111)
            ).scalar_one()

            assert updated.subscribed_events == {SUBSCRIPTION_STARTUP: True}
        finally:
            session.close()
            engine.dispose()

    def test_returns_false_for_nonexistent_user(self):
        """Test that False is returned for nonexistent user."""
        engine, session = create_sqlite_session()
        try:
            result = subscribe_user_to_startup(session, 999)
            assert result is False
        finally:
            session.close()
            engine.dispose()


class TestUnsubscribeUserFromStartup:
    """Tests for unsubscribe_user_from_startup function."""

    def test_unsubscribes_existing_user(self):
        """Test that existing user can be unsubscribed."""
        engine, session = create_sqlite_session()
        try:
            user = TelegramUser(
                telegram_id=111,
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )
            session.add(user)
            session.commit()

            result = unsubscribe_user_from_startup(session, 111)

            assert result is True

            updated = session.execute(
                select(TelegramUserModel).where(TelegramUserModel.telegram_id == 111)
            ).scalar_one()

            assert updated.subscribed_events == {SUBSCRIPTION_STARTUP: False}
        finally:
            session.close()
            engine.dispose()

    def test_returns_false_for_nonexistent_user(self):
        """Test that False is returned for nonexistent user."""
        engine, session = create_sqlite_session()
        try:
            result = unsubscribe_user_from_startup(session, 999)
            assert result is False
        finally:
            session.close()
            engine.dispose()


class TestUpsertTelegramUserWithSubscriptions:
    """Tests that upsert_telegram_user works with subscription system."""

    def test_new_user_has_empty_subscriptions(self):
        """Test that new users have empty subscriptions by default."""
        engine, session = create_sqlite_session()
        try:
            user = upsert_telegram_user(
                session,
                telegram_id=111,
                first_name="New",
                last_name="User",
            )

            assert user.subscribed_events == {}
            assert user.is_active is False
        finally:
            session.close()
            engine.dispose()

    def test_upsert_preserves_subscriptions(self):
        """Test that upsert doesn't clear existing subscriptions."""
        engine, session = create_sqlite_session()
        try:
            # Create user with subscription
            user = TelegramUser(
                telegram_id=111,
                is_active=True,
                subscribed_events={SUBSCRIPTION_STARTUP: True},
            )
            session.add(user)
            session.commit()

            # Upsert with new name
            updated = upsert_telegram_user(
                session,
                telegram_id=111,
                first_name="Updated",
                last_name="Name",
            )

            assert updated.first_name == "Updated"
            assert updated.subscribed_events == {SUBSCRIPTION_STARTUP: True}
            assert updated.is_active is True
        finally:
            session.close()
            engine.dispose()
