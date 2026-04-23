from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Requirement(SQLModel, table=True):
    __tablename__ = "requirement"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None
    markdown_content: Optional[str] = None
    status: str = Field(default="pending", index=True)
    verification_prompt: Optional[str] = None
    is_test: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    
    # Queue-Steuerung und Statusmodell
    queue_status: str = Field(default="backlog", index=True, description="Kanban-Status: backlog, in_progress, review, done, trash")
    type: str = Field(default="artifact", description="Typ: transcript oder artifact")
    has_work_packages: bool = Field(default=False, description="Flag: Existieren WorkPackages für dieses Requirement")
    order_number: int = Field(default=0, description="Reihenfolge in der Queue")
    scheduler_enabled: bool = Field(default=True, description="Erlaubt automatische Verarbeitung durch Scheduler")
    parallelization_delay: int = Field(default=0, description="Delay in Sekunden zwischen parallelen Tasks")
