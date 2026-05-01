"""Alembic environment configuration for ExecQueue."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from execqueue.db.base import metadata
from execqueue.db.runtime import get_database_url
from execqueue.settings import get_settings

import execqueue.db.models  # noqa: F401  Ensures model metadata is registered.
import execqueue.orchestrator.workflow_models  # noqa: F401  Ensures Workflow model metadata is registered.

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def get_alembic_url() -> str:
    """Resolve the migration database URL from the shared settings."""
    return get_database_url(get_settings())


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_alembic_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_alembic_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
