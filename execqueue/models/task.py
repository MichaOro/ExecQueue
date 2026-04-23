from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import BigInteger


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OpenCodeSessionStatus(str, Enum):
    """Status einer OpenCode Session."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_type: str = Field(index=True)
    source_id: int = Field(index=True, sa_type=BigInteger)  # BIGINT für Telegram User IDs (zu groß für INTEGER)
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
    
    # Queue-Steuerung und Statusmodell
    block_queue: bool = Field(default=False, description="Blockiert die Queue für andere Tasks")
    parallelization_allowed: bool = Field(default=True, description="Erlaubt parallele Ausführung mit anderen Tasks")
    schedulable: bool = Field(default=True, description="Erlaubt automatische Verarbeitung durch Scheduler")
    queue_status: str = Field(default="backlog", index=True, description="Kanban-Status: backlog, in_progress, review, done, trash")
    
    # OpenCode ACP Session-Metadaten
    opencode_session_id: Optional[str] = Field(default=None, index=True, description="OpenCode ACP Session ID")
    opencode_project_path: Optional[str] = Field(default=None, description="Project directory for OpenCode session")
    opencode_status: OpenCodeSessionStatus = Field(default=OpenCodeSessionStatus.PENDING, index=True, description="OpenCode session status")
    opencode_last_ping: Optional[datetime] = Field(default=None, description="Last heartbeat/ping timestamp")
