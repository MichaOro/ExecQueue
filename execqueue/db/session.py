"""SQLAlchemy session factory and lifecycle helpers."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from execqueue.db.engine import build_engine, get_engine
from execqueue.settings import Settings


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the provided engine."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the cached application session factory."""
    return build_session_factory(get_engine())


def create_session(settings: Settings | None = None) -> Session:
    """Create a new SQLAlchemy session for application code outside FastAPI."""
    if settings is None:
        factory = get_session_factory()
    else:
        factory = build_session_factory(build_engine(settings))
    return factory()


def get_session(settings: Settings | None = None) -> Iterator[Session]:
    """Yield a request-scoped session and ensure it closes afterwards."""
    session = create_session(settings)
    try:
        yield session
    finally:
        session.close()
