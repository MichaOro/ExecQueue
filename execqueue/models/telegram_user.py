from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelegramUser(SQLModel, table=True):
    """Telegram-Benutzer-Entität für Bot-Autorisierung und Subscriptions."""
    
    __tablename__ = "telegram_user"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: str = Field(unique=True, index=True, description="Telegram Benutzer-ID")
    username: Optional[str] = Field(default=None, description="Telegram Username (ohne @)")
    first_name: Optional[str] = Field(default=None)
    last_name: Optional[str] = Field(default=None)
    role: str = Field(default="observer", description="Rolle: observer | operator | admin")
    subscribed_events: str = Field(default="{}", description="JSON-String mit abonnierten Events")
    is_active: bool = Field(default=True, description="Ist Benutzer aktiv?")
    last_active: datetime = Field(default_factory=utcnow, description="Letzte Aktivität")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    is_test: bool = Field(default=False, description="Test-Daten-Flag")
