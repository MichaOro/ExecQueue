"""Authentication and authorization helpers for Telegram bot."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from execqueue.db.models import TelegramUser
from execqueue.db.session import create_session


def get_user_info(telegram_id: int) -> tuple[str | None, bool]:
    """Get user role and active status.

    Args:
        telegram_id: The Telegram user ID.

    Returns:
        tuple: (role or None, is_active)
    """
    session = create_session()
    try:
        user = session.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        ).scalar_one_or_none()
        if user is None:
            return None, False
        return user.role, user.is_active
    finally:
        session.close()


def has_required_role(telegram_id: int, required_roles: list[str]) -> bool:
    """Check if user has one of the required roles and is active.

    Args:
        telegram_id: The Telegram user ID.
        required_roles: List of allowed roles.

    Returns:
        True if user is active and has one of the required roles.
    """
    role, is_active = get_user_info(telegram_id)
    return is_active and role in required_roles
