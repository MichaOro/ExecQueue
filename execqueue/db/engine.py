"""SQLAlchemy engine creation for ExecQueue."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from execqueue.db.runtime import get_database_url
from execqueue.settings import Settings, get_settings


def build_engine(settings: Settings) -> Engine:
    """Build a SQLAlchemy engine for the configured database target."""
    database_url = get_database_url(settings)
    url = make_url(database_url)

    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
        database_url = url.render_as_string(hide_password=False)

    engine_kwargs: dict[str, object] = {
        "echo": settings.database_echo,
        "pool_pre_ping": settings.database_pool_pre_ping,
    }

    if url.get_backend_name().startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = settings.database_pool_size
        engine_kwargs["max_overflow"] = settings.database_max_overflow
        engine_kwargs["pool_timeout"] = settings.database_pool_timeout

    return create_engine(database_url, **engine_kwargs)


@lru_cache
def get_engine() -> Engine:
    """Return the cached application engine."""
    return build_engine(get_settings())
