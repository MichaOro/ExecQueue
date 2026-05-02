"""Workflow data models for orchestrator crash recovery.

Implements REQ-015 WP01: Workflow Data Model & Migration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from execqueue.db.base import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class WorkflowStatus(str, Enum):
    """Workflow lifecycle states."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class PreparedExecutionContext:
    """Represents a single prepared task execution context."""

    task_id: UUID
    branch_name: str
    worktree_path: str
    commit_sha: str | None


@dataclass
class WorkflowContext:
    """Runtime context for workflow execution.

    Used for crash recovery and state persistence.
    
    Lifecycle fields (started_at, finished_at, error_message) enable
    detailed audit trails and crash recovery diagnostics.
    """

    workflow_id: UUID
    epic_id: UUID | None
    requirement_id: UUID | None
    tasks: list[PreparedExecutionContext] = field(default_factory=list)
    dependencies: dict[UUID, list[UUID]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class Workflow(Base):
    """Workflow table for orchestrator crash recovery.

    Tracks the state of workflow execution across restarts.
    
    Additional audit fields (started_at, finished_at, error_message) enable
    detailed lifecycle tracking and crash recovery diagnostics.
    """

    __tablename__ = "workflow"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ck_workflow_status_allowed",
        ),
        Index("ix_workflow_status", "status"),
        Index("ix_workflow_epic_id", "epic_id"),
        Index("ix_workflow_requirement_id", "requirement_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    epic_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    requirement_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=WorkflowStatus.RUNNING.value,
        server_default=WorkflowStatus.RUNNING.value,
    )
    runner_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Lifecycle audit fields for crash recovery and observability
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        String(4096),  # Allow up to 4KB for detailed error messages
        nullable=True,
    )
