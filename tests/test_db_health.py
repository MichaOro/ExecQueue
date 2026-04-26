"""Tests for database health check behavior."""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from execqueue.db.health import get_database_healthcheck


def test_database_healthcheck_returns_ok_when_query_succeeds(monkeypatch):
    class DummySession:
        closed = False

        def execute(self, _query) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    session = DummySession()
    monkeypatch.setattr("execqueue.db.health.create_session", lambda: session)

    result = get_database_healthcheck()

    assert result.component == "database"
    assert result.status == "OK"
    assert "succeeded" in result.detail.lower()
    assert session.closed is True


def test_database_healthcheck_returns_degraded_when_query_fails(monkeypatch):
    class DummySession:
        closed = False

        def execute(self, _query) -> None:
            raise SQLAlchemyError("postgresql://user:secret@db.example.com/execqueue")

        def close(self) -> None:
            self.closed = True

    session = DummySession()
    monkeypatch.setattr("execqueue.db.health.create_session", lambda: session)

    result = get_database_healthcheck()

    assert result.component == "database"
    assert result.status == "DEGRADED"
    assert result.detail == "Database connectivity check failed."
    assert "secret" not in result.detail.lower()
    assert session.closed is True


def test_database_healthcheck_returns_degraded_when_db_is_unconfigured(monkeypatch):
    monkeypatch.setattr(
        "execqueue.db.health.create_session",
        lambda: (_ for _ in ()).throw(ValueError("DATABASE_URL=secret")),
    )

    result = get_database_healthcheck()

    assert result.component == "database"
    assert result.status == "DEGRADED"
    assert result.detail == "Database health check is not fully configured."
    assert "secret" not in result.detail.lower()


def test_database_healthcheck_returns_degraded_when_driver_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "execqueue.db.health.create_session",
        lambda: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'psycopg2'")),
    )

    result = get_database_healthcheck()

    assert result.component == "database"
    assert result.status == "DEGRADED"
    assert result.detail == "Database health check could not initialize its database driver."
