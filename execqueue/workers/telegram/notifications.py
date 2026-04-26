"""Telegram notification service for subscriber management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from execqueue.db.models import TelegramUser
from execqueue.settings import get_settings

logger = logging.getLogger(__name__)

SUBSCRIPTION_STARTUP = "TELEGRAM_NOTIFICATION_STARTUP"


def get_startup_notification_recipients(session: Session) -> list[int]:
    """Get list of Telegram user IDs that should receive startup notifications.

    Returns active users who have subscribed to TELEGRAM_NOTIFICATION_STARTUP.
    No legacy fallback - fully DB-based.
    """
    try:
        from sqlalchemy import inspect

        # Check if we're using PostgreSQL (has JSONB support) or SQLite
        dialect_name = inspect(session.bind).dialect.name

        if dialect_name == "postgresql":
            # Use PostgreSQL JSONB operator
            from sqlalchemy import text
            result = session.execute(
                text("""
                    SELECT telegram_id 
                    FROM telegram_users 
                    WHERE is_active = true 
                    AND subscribed_events->>'TELEGRAM_NOTIFICATION_STARTUP' = 'true'
                """)
            )
            return [row[0] for row in result]
        else:
            # Fallback for SQLite and other databases - load all and filter in Python
            from sqlalchemy import select
            users = session.execute(
                select(TelegramUser).where(
                    TelegramUser.is_active == True  # noqa: E712
                )
            ).scalars().all()

            return [
                user.telegram_id for user in users
                if user.subscribed_events.get(SUBSCRIPTION_STARTUP, False) is True
            ]
    except Exception:
        logger.exception("Failed to query startup notification recipients from database")
        return []


def build_startup_message() -> str:
    """Build the startup notification message."""
    return (
        "\U0001F7E2 *Bot Online*\n\n"
        "Der ExecQueue Bot ist jetzt online und steht zur Verfuegung.\n"
        f"Startzeit: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )


def update_user_last_active(session: Session, telegram_id: int) -> None:
    """Update last_active timestamp for a Telegram user.

    Silently ignores users that don't exist.
    """
    try:
        user = session.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        ).scalar_one_or_none()

        if user is not None:
            user.last_active = datetime.now(timezone.utc)
            session.commit()
    except Exception:
        logger.exception("Failed to update last_active for user %s", telegram_id)
        session.rollback()


def is_user_subscribed_to_startup(session: Session, telegram_id: int) -> bool:
    """Check if a specific user is subscribed to startup notifications."""
    try:
        user = session.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        ).scalar_one_or_none()

        if user is None:
            return False

        return user.is_active and user.subscribed_events.get(SUBSCRIPTION_STARTUP, False)
    except Exception:
        logger.exception("Failed to check subscription status for user %s", telegram_id)
        return False
