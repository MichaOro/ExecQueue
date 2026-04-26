"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from execqueue.db.session import get_session


def get_db_session() -> Iterator[Session]:
    """Provide a request-scoped SQLAlchemy session."""
    yield from get_session()


DatabaseSession = Annotated[Session, Depends(get_db_session)]
