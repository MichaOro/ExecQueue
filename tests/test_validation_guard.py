"""Tests for pytest DB safety validation."""

from __future__ import annotations

import pytest

from tests.conftest import validate_pytest_database_configuration


def test_validation_guard_rejects_production_app_env():
    with pytest.raises(pytest.UsageError, match="APP_ENV=production"):
        validate_pytest_database_configuration(
            {
                "APP_ENV": "production",
                "DATABASE_URL": "postgresql://user:secret@localhost:5432/execqueue",
                "DATABASE_URL_TEST": "postgresql://user:secret@localhost:5432/execqueue_test",
            }
        )


def test_validation_guard_rejects_identical_database_urls():
    with pytest.raises(pytest.UsageError, match="same database"):
        validate_pytest_database_configuration(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "postgresql://user:secret@localhost:5432/execqueue",
                "DATABASE_URL_TEST": "postgresql://user:secret@localhost:5432/execqueue",
            }
        )


def test_validation_guard_accepts_isolated_test_setup():
    validate_pytest_database_configuration(
        {
            "APP_ENV": "test",
            "DATABASE_URL": "postgresql://user:secret@localhost:5432/execqueue",
            "DATABASE_URL_TEST": "sqlite+pysqlite:///tmp/execqueue_test.sqlite3",
        }
    )
