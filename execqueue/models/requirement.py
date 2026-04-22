from typing import Optional
from datetime import datetime, timezone

from sqlmodel import SQLModel, Field

from execqueue.runtime import is_test_mode


class Requirement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str
    markdown_content: str
    verification_prompt: Optional[str] = None
    status: str = "backlog"
    is_test: bool = Field(default_factory=is_test_mode, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
