"""Tests for task ORM defaults and constraints."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict
from sqlalchemy.exc import IntegrityError

from execqueue.db.base import Base
from execqueue.db.engine import build_engine
from execqueue.db.models import Task
from execqueue.db.session import build_session_factory
from execqueue.settings import RuntimeEnvironment, Settings


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


def test_task_defaults_are_applied():
    engine, session = create_sqlite_session()
    try:
        task = Task(
            task_number=1,
            prompt="Build the release notes",
            type="task",
            max_retries=3,
            created_by_type="user",
            created_by_ref="123456789",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        assert task.title == ""
        assert task.status == "backlog"
        assert task.retry_count == 0
        assert task.execution_order is None
        assert task.session_id is None
        assert task.project_id is None
        assert task.details == {}
    finally:
        session.close()
        engine.dispose()


def test_task_created_by_type_constraint_rejects_invalid_values():
    engine, session = create_sqlite_session()
    try:
        task = Task(
            task_number=1,
            title="Invalid creator",
            prompt="This should fail",
            type="task",
            max_retries=1,
            created_by_type="service",
            created_by_ref="internal",
        )
        session.add(task)

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError(
                "Expected created_by_type constraint to reject invalid role values."
            )
    finally:
        session.close()
        engine.dispose()
