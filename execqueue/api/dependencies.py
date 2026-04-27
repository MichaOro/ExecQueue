"""Shared FastAPI dependencies."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from execqueue.db.session import get_session
from execqueue.settings import get_settings


def get_db_session() -> Iterator[Session]:
    """Provide a request-scoped SQLAlchemy session."""
    yield from get_session()


def require_system_admin(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    """Require the shared admin token for privileged system operations."""
    configured_token = get_settings().system_admin_token

    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System admin API token is not configured.",
        )

    if not x_admin_token or not secrets.compare_digest(x_admin_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )


DatabaseSession = Annotated[Session, Depends(get_db_session)]
