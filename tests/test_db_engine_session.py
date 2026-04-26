"""Tests for SQLAlchemy engine, session, and FastAPI DI helpers."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_settings import SettingsConfigDict
from sqlalchemy.orm import Session

from execqueue.api.dependencies import DatabaseSession
from execqueue.db.engine import build_engine
from execqueue.db.session import build_session_factory, get_session
from execqueue.settings import RuntimeEnvironment, Settings


class RuntimeTestSettings(Settings):
    """Settings variant that ignores the local .env file during tests."""

    model_config = SettingsConfigDict(env_file="", extra="ignore")


def test_build_engine_supports_sqlite_for_tests():
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.TEST,
        database_url_test="sqlite+pysqlite:///:memory:",
    )

    engine = build_engine(settings)

    assert engine.dialect.name == "sqlite"
    assert str(engine.url) == "sqlite+pysqlite:///:memory:"
    engine.dispose()


def test_build_engine_uses_configured_postgres_url_without_connecting():
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.PRODUCTION,
        database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
    )

    engine = build_engine(settings)

    assert engine.dialect.name == "postgresql"
    assert str(engine.url) == "postgresql+psycopg://user:***@localhost:5432/execqueue"
    engine.dispose()


def test_build_engine_upgrades_plain_postgres_url_to_psycopg_driver():
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.PRODUCTION,
        database_url="postgresql://user:secret@localhost:5432/execqueue",
    )

    engine = build_engine(settings)

    assert engine.dialect.name == "postgresql"
    assert str(engine.url) == "postgresql+psycopg://user:***@localhost:5432/execqueue"
    engine.dispose()


def test_build_session_factory_creates_sqlalchemy_sessions():
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.TEST,
        database_url_test="sqlite+pysqlite:///:memory:",
    )
    engine = build_engine(settings)
    factory = build_session_factory(engine)

    session = factory()

    assert isinstance(session, Session)
    assert session.bind is engine
    assert session.expire_on_commit is False

    session.close()
    engine.dispose()


def test_get_session_closes_session_after_use(monkeypatch):
    closed = False

    class DummySession:
        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr("execqueue.db.session.create_session", lambda settings=None: DummySession())

    generator = get_session()
    yielded = next(generator)

    assert isinstance(yielded, DummySession)

    generator.close()

    assert closed is True


def test_fastapi_dependency_injection_provides_request_scoped_session(monkeypatch):
    app = FastAPI()
    dummy_session = object()

    def fake_get_session():
        yield dummy_session

    monkeypatch.setattr("execqueue.api.dependencies.get_session", fake_get_session)

    @app.get("/session")
    def read_session(db: DatabaseSession) -> dict[str, bool]:
        return {"same_object": db is dummy_session}

    client = TestClient(app)

    response = client.get("/session")

    assert response.status_code == 200
    assert response.json() == {"same_object": True}
