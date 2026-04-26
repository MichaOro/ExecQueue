"""Tests for Alembic setup and schema migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def build_alembic_config(database_url: str) -> Config:
    """Create an Alembic config bound to a temporary test database."""
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_project_and_telegram_user_migrations_upgrade_and_downgrade(tmp_path, monkeypatch):
    database_path = tmp_path / "alembic_test.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL_TEST", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    config = build_alembic_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert "project" in inspector.get_table_names()
    assert "telegram_users" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("project")}
    assert columns == {
        "id",
        "key",
        "name",
        "description",
        "is_active",
        "created_at",
        "updated_at",
    }

    unique_constraints = inspector.get_unique_constraints("project")
    unique_names = {constraint["name"] for constraint in unique_constraints}
    assert "uq_project_key" in unique_names

    telegram_columns = {column["name"] for column in inspector.get_columns("telegram_users")}
    assert telegram_columns == {
        "id",
        "telegram_id",
        "first_name",
        "last_name",
        "role",
        "subscribed_events",
        "is_active",
        "last_active",
        "created_at",
        "updated_at",
    }

    telegram_unique_constraints = inspector.get_unique_constraints("telegram_users")
    telegram_unique_names = {constraint["name"] for constraint in telegram_unique_constraints}
    assert "uq_telegram_users_telegram_id" in telegram_unique_names

    check_constraints = inspector.get_check_constraints("telegram_users")
    check_names = {constraint["name"] for constraint in check_constraints}
    assert "ck_telegram_users_telegram_users_role_allowed" in check_names

    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "20260426_02"

    command.downgrade(config, "base")

    inspector = inspect(engine)
    assert "project" not in inspector.get_table_names()
    assert "telegram_users" not in inspector.get_table_names()
    engine.dispose()
