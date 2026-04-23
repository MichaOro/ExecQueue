from contextlib import contextmanager
from sqlmodel import Session
from execqueue.db.engine import engine


def get_session():
    """Get a database session (generator for FastAPI dependency)."""
    with Session(engine) as session:
        yield session
