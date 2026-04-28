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


def test_project_telegram_user_and_task_migrations_upgrade_and_downgrade(tmp_path, monkeypatch):
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
    assert "task" in inspector.get_table_names()
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

    task_columns = {column["name"] for column in inspector.get_columns("task")}
    # Expected columns include original columns plus REQ-011 execution preparation fields
    expected_task_columns = {
        "id",
        "task_number",
        "title",
        "prompt",
        "type",
        "status",
        "execution_order",
        "retry_count",
        "max_retries",
        "session_id",
        "created_by_type",
        "created_by_ref",
        "project_id",
        "requirement_id",
        "idempotency_key",
        "details",
        "created_at",
        "updated_at",
        # REQ-011 execution preparation fields
        "queued_at",
        "locked_by",
        "preparation_attempt_count",
        "last_preparation_error",
        "branch_name",
        "worktree_path",
        "commit_sha_before",
        "prepared_context_version",
        "batch_id",
    }
    assert task_columns == expected_task_columns

    task_unique_constraints = inspector.get_unique_constraints("task")
    task_unique_names = {constraint["name"] for constraint in task_unique_constraints}
    assert "uq_task_task_number" in task_unique_names
    assert "uq_task_idempotency_key" in task_unique_names

    task_foreign_keys = inspector.get_foreign_keys("task")
    foreign_key_names = {foreign_key["name"] for foreign_key in task_foreign_keys}
    assert "fk_task_project_id_project" in foreign_key_names
    assert "fk_task_requirement_id_requirement" in foreign_key_names

    task_indexes = inspector.get_indexes("task")
    task_index_names = {index["name"] for index in task_indexes}
    assert "ix_task_status" in task_index_names
    assert "ix_task_type" in task_index_names
    assert "ix_task_requirement_id" in task_index_names

    task_checks = inspector.get_check_constraints("task")
    task_check_names = {constraint["name"] for constraint in task_checks}
    assert "ck_task_task_created_by_type_allowed" in task_check_names

    # Verify requirement table exists with correct structure
    assert "requirement" in inspector.get_table_names()
    requirement_columns = {column["name"] for column in inspector.get_columns("requirement")}
    assert requirement_columns == {
        "id",
        "title",
        "description",
        "status",
        "project_id",
        "created_at",
        "updated_at",
    }

    requirement_indexes = inspector.get_indexes("requirement")
    requirement_index_names = {index["name"] for index in requirement_indexes}
    assert "ix_requirement_status" in requirement_index_names
    assert "ix_requirement_project_id" in requirement_index_names

    requirement_checks = inspector.get_check_constraints("requirement")
    requirement_check_names = {constraint["name"] for constraint in requirement_checks}
    assert "ck_requirement_status_allowed" in requirement_check_names

    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "99d5a553d696"  # Updated to include REQ-011 migration

    command.downgrade(config, "base")

    inspector = inspect(engine)
    assert "project" not in inspector.get_table_names()
    assert "telegram_users" not in inspector.get_table_names()
    assert "task" not in inspector.get_table_names()
    engine.dispose()
