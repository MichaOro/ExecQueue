from typing import Optional
from datetime import datetime, timezone

from sqlmodel import SQLModel, Field

from execqueue.runtime import is_test_mode


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)

    source_type: str = Field(index=True)  # "requirement" | "work_package"
    source_id: int = Field(index=True)

    title: str
    prompt: str
    verification_prompt: Optional[str] = None

    status: str = Field(default="queued", index=True)
    execution_order: int = Field(default=0, index=True)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=5)

    last_result: Optional[str] = None

    is_test: bool = Field(default_factory=is_test_mode, index=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
