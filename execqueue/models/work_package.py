from typing import Optional
from datetime import datetime, timezone

from sqlmodel import SQLModel, Field


class WorkPackage(SQLModel, table=True):
    __tablename__ = "work_packages"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Verbindung zum Requirement (Epic)
    requirement_id: int = Field(foreign_key="requirement.id", index=True)

    title: str
    description: str

    # wichtig für Queue
    status: str = Field(default="backlog", index=True)

    # Reihenfolge innerhalb eines Epics
    execution_order: int = Field(default=0, index=True)

    # Prompt für OpenCode
    implementation_prompt: Optional[str] = None

    # wie geprüft wird ob fertig
    verification_prompt: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))