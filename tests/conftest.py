"""Shared pytest safety guards for ExecQueue."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from execqueue.db.engine import get_engine
from execqueue.db.session import get_session_factory
from execqueue.settings import get_settings


def validate_pytest_database_configuration(environment: dict[str, str] | None = None) -> None:
    """Reject unsafe DB test configurations before the suite runs."""
    env = environment or os.environ
    app_env = env.get("APP_ENV", "").strip().lower()
    database_url = env.get("DATABASE_URL", "").strip()
    database_url_test = env.get("DATABASE_URL_TEST", "").strip()

    if app_env == "production":
        raise pytest.UsageError(
            "pytest must not run with APP_ENV=production. Use APP_ENV=test and DATABASE_URL_TEST."
        )

    if database_url and database_url_test and database_url == database_url_test:
        raise pytest.UsageError(
            "pytest must not run when DATABASE_URL and DATABASE_URL_TEST point to the same database."
        )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Validate global DB safety before collecting tests."""
    validate_pytest_database_configuration()
    settings = get_settings()
    validate_pytest_database_configuration(
        {
            "APP_ENV": settings.app_env.value,
            "DATABASE_URL": settings.database_url or "",
            "DATABASE_URL_TEST": settings.database_url_test or "",
        }
    )


@pytest.fixture(autouse=True)
def clear_runtime_caches():
    """Keep settings and DB runtime caches isolated across tests."""
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    try:
        yield
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def stub_task_orchestrator_trigger(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """Prevent ordinary tests from triggering the real orchestrator on task creation.

    Tests that explicitly verify trigger_orchestrator() itself keep the real implementation.
    """
    if request.node.module.__name__.endswith("test_orchestrator_trigger"):
        yield
        return

    monkeypatch.setattr(
        "execqueue.tasks.service.trigger_orchestrator",
        MagicMock(return_value=True),
    )
    yield
