from typing import Optional
from datetime import datetime, timezone

from sqlmodel import SQLModel, Field

from execqueue.runtime import is_test_mode


class WorkPackage(SQLModel, table=True):
    __tablename__ = "work_packages"

    id: Optional[int] = Field(default=None, primary_key=True)

    requirement_id: int = Field(foreign_key="requirement.id", index=True)

    title: str
    description: str

    status: str = Field(default="backlog", index=True)

    execution_order: int = Field(default=0, index=True)

    implementation_prompt: Optional[str] = None

    verification_prompt: Optional[str] = None

    is_test: bool = Field(default_factory=is_test_mode, index=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
