from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_type: str = Field(index=True)
    source_id: int = Field(index=True)
    title: str
    prompt: str
    verification_prompt: Optional[str] = None
    status: str = Field(default="queued", index=True)
    execution_order: int = Field(default=0, index=True)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=5)
    last_result: Optional[str] = None
    is_test: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    scheduled_after: Optional[datetime] = Field(default=None, index=True)
    locked_at: Optional[datetime] = Field(default=None, index=True, description="Timestamp when task was locked for processing")
    locked_by: Optional[str] = Field(default=None, index=True, description="Worker instance ID that locked the task")
