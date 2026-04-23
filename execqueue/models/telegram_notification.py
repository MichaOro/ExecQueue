from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelegramNotification(SQLModel, table=True):
    """Benachrichtigung für Telegram-Bot."""
    
    __tablename__ = "telegram_notification"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_telegram_id: str = Field(index=True, description="Telegram Benutzer-ID")
    event_type: str = Field(
        index=True,
        description="Event-Typ: task_completed | validation_failed | retry_exhausted | scheduler_started | scheduler_stopped"
    )
    task_id: Optional[int] = Field(default=None, description="Optional: Referenz zu Task")
    message: str = Field(description="Benachrichtigungstext")
    is_read: bool = Field(default=False, description="Ist die Nachricht gelesen?")
    sent_at: Optional[datetime] = Field(default=None, description="Wann gesendet (NULL = noch nicht gesendet)")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    is_test: bool = Field(default=False, description="Test-Daten-Flag")
