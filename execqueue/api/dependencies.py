"""Shared FastAPI dependencies."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from execqueue.db.models import TelegramUser
from execqueue.db.session import create_session, get_session
from execqueue.settings import get_settings


def get_db_session() -> Iterator[Session]:
    """Provide a request-scoped SQLAlchemy session."""
    yield from get_session()


def require_system_admin(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    x_telegram_user_id: Annotated[str | None, Header(alias="X-Telegram-User-ID")] = None,
) -> None:
    """Require authentication for privileged system operations.
    
    Supports two authentication methods:
    1. Telegram user ID header (X-Telegram-User-ID): Validates against database
    2. Admin token header (X-Admin-Token): Validates against configured token
    
    Telegram authentication takes precedence when both headers are provided.
    """
    # Method 1: Telegram user ID authentication (preferred for internal bot)
    if x_telegram_user_id:
        try:
            telegram_id = int(x_telegram_user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Telegram user ID format.",
            )
        
        # Lazily create a DB session only when needed
        session = create_session()
        try:
            user = session.execute(
                select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
            ).scalar_one_or_none()
        finally:
            session.close()
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Telegram user not found.",
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Telegram user account is not active.",
            )
        
        if user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required for this operation.",
            )
        
        return
    
    # Method 2: Admin token authentication (for external clients)
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
