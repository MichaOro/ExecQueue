"""Tests for database runtime helpers."""

from pydantic_settings import SettingsConfigDict

from execqueue.db.runtime import describe_database_target, get_database_url
from execqueue.settings import RuntimeEnvironment, Settings


class RuntimeTestSettings(Settings):
    """Settings variant that ignores the local .env file during tests."""

    model_config = SettingsConfigDict(env_file="", extra="ignore")


def test_get_database_url_uses_primary_database_in_development():
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.DEVELOPMENT,
        database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
    )

    assert (
        get_database_url(settings)
        == "postgresql+psycopg://user:secret@localhost:5432/execqueue"
    )


def test_get_database_url_uses_test_database_in_test_environment():
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.TEST,
        database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
        database_url_test="postgresql+psycopg://tester:secret@localhost:5432/execqueue_test",
    )

    assert (
        get_database_url(settings)
        == "postgresql+psycopg://tester:secret@localhost:5432/execqueue_test"
    )


def test_get_database_url_requires_dedicated_test_database():
    settings = RuntimeTestSettings(app_env=RuntimeEnvironment.TEST)

    try:
        get_database_url(settings)
    except ValueError as exc:
        assert "DATABASE_URL_TEST" in str(exc)
    else:
        raise AssertionError("Expected ValueError when test database URL is missing.")


def test_describe_database_target_redacts_credentials():
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.PRODUCTION,
        database_url="postgresql+psycopg://execqueue:super-secret@db.example.com:5432/execqueue",
    )

    description = describe_database_target(settings)

    assert description == {
        "environment": "production",
        "role": "primary",
        "dsn": "postgresql+psycopg://execqueue:***@db.example.com:5432/execqueue",
    }
