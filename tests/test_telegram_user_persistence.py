"""Tests for Telegram user ORM defaults and persistence helpers."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict
from sqlalchemy.exc import IntegrityError

from execqueue.db.base import Base
from execqueue.db.engine import build_engine
from execqueue.db.models import TelegramUser
from execqueue.db.session import build_session_factory
from execqueue.settings import RuntimeEnvironment, Settings
from execqueue.workers.telegram.persistence import upsert_telegram_user


class RuntimeTestSettings(Settings):
    """Settings variant that ignores the local .env file during tests."""

    model_config = SettingsConfigDict(env_file="", extra="ignore")


def create_sqlite_session():
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.TEST,
        database_url_test="sqlite+pysqlite:///:memory:",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session = build_session_factory(engine)()
    return engine, session


def test_telegram_user_defaults_are_applied():
    engine, session = create_sqlite_session()
    try:
        user = TelegramUser(
            telegram_id=123456789,
            first_name="Ada",
            last_name="Lovelace",
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.role == "user"
        assert user.subscribed_events == {}
        assert user.is_active is False
        assert user.last_active is None
    finally:
        session.close()
        engine.dispose()


def test_telegram_user_role_constraint_rejects_invalid_values():
    engine, session = create_sqlite_session()
    try:
        user = TelegramUser(
            telegram_id=987654321,
            first_name="Grace",
            role="owner",
        )
        session.add(user)

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Expected role constraint to reject invalid role values.")
    finally:
        session.close()
        engine.dispose()


def test_upsert_telegram_user_creates_and_updates_existing_user():
    engine, session = create_sqlite_session()
    try:
        created = upsert_telegram_user(
            session,
            telegram_id=42,
            first_name="Linus",
            last_name=None,
        )

        assert created.telegram_id == 42
        assert created.first_name == "Linus"
        assert created.is_active is False
        assert created.last_active is not None

        updated = upsert_telegram_user(
            session,
            telegram_id=42,
            first_name="Linus",
            last_name="Torvalds",
        )

        assert updated.id == created.id
        assert updated.last_name == "Torvalds"

        users = session.query(TelegramUser).all()
        assert len(users) == 1
    finally:
        session.close()
        engine.dispose()
