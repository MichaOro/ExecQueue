"""Persistence helpers for Telegram user lifecycle events."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from execqueue.db.models import TelegramUser
from execqueue.workers.telegram.notifications import SUBSCRIPTION_STARTUP

__all__ = ["upsert_telegram_user", "subscribe_user_to_startup", "unsubscribe_user_from_startup"]


def upsert_telegram_user(
    session: Session,
    *,
    telegram_id: int,
    first_name: str | None,
    last_name: str | None,
    last_active: datetime | None = None,
) -> TelegramUser:
    """Create or update a Telegram user row from message metadata.

    New users are created with is_active=False and empty subscriptions.
    last_active is updated on both create and update.
    """
    user = session.execute(
        select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
    ).scalar_one_or_none()

    if user is None:
        user = TelegramUser(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
    else:
        user.first_name = first_name
        user.last_name = last_name

    user.last_active = last_active or datetime.now(timezone.utc)

    session.commit()
    session.refresh(user)
    return user


def subscribe_user_to_startup(session: Session, telegram_id: int) -> bool:
    """Subscribe a user to startup notifications.

    Returns True if subscription was set, False if user not found.
    """
    user = session.execute(
        select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
    ).scalar_one_or_none()

    if user is None:
        return False

    user.subscribed_events[SUBSCRIPTION_STARTUP] = True
    session.commit()
    return True


def unsubscribe_user_from_startup(session: Session, telegram_id: int) -> bool:
    """Unsubscribe a user from startup notifications.

    Returns True if unsubscription was performed, False if user not found.
    """
    user = session.execute(
        select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
    ).scalar_one_or_none()

    if user is None:
        return False

    user.subscribed_events[SUBSCRIPTION_STARTUP] = False
    session.commit()
    return True
