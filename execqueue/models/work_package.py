from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone
from execqueue.models.task import OpenCodeSessionStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkPackage(SQLModel, table=True):
    __tablename__ = "work_packages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    requirement_id: int = Field(index=True)
    title: str
    description: Optional[str] = None
    implementation_prompt: Optional[str] = None
    execution_order: int = Field(default=0)
    verification_prompt: Optional[str] = None
    status: str = Field(default="pending", index=True)
    is_test: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    
    # Queue-Steuerung und Statusmodell
    queue_status: str = Field(default="backlog", index=True, description="Kanban-Status: backlog, in_progress, review, done, trash")
    order_number: int = Field(default=0, description="Reihenfolge in der Queue")
    dependency_id: Optional[int] = Field(default=None, foreign_key="work_packages.id", description="Dependency auf anderes WorkPackage")
    parallelization_enabled: bool = Field(default=False, description="Erlaubt parallele Ausführung")
    
    # OpenCode ACP Session-Metadaten
    opencode_session_id: Optional[str] = Field(default=None, index=True, description="OpenCode ACP Session ID")
    opencode_project_path: Optional[str] = Field(default=None, description="Project directory for OpenCode session")
    opencode_status: OpenCodeSessionStatus = Field(default=OpenCodeSessionStatus.PENDING, index=True, description="OpenCode session status")
    opencode_last_ping: Optional[datetime] = Field(default=None, description="Last heartbeat/ping timestamp")
