from contextlib import contextmanager
from sqlmodel import Session
from execqueue.db.engine import engine


@contextmanager
def get_session():
    """Get a database session."""
    with Session(engine) as session:
        yield session
