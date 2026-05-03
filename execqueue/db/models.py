"""Database models for ExecQueue."""

from __future__ import annotations

from typing import Any
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    BIGINT,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from execqueue.db.base import Base


class TelegramUserRole(str, Enum):
    """Supported application roles for Telegram users."""

    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"


class TaskCreatedByType(str, Enum):
    """Supported task creator types."""

    USER = "user"
    AGENT = "agent"


class TaskType(str, Enum):
    """Supported executable task types."""

    PLANNING = "planning"
    EXECUTION = "execution"
    ANALYSIS = "analysis"
    REQUIREMENT = "requirement"


class RequirementStatus(str, Enum):
    """Supported requirement lifecycle states."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    """Task lifecycle states for REQ-011 orchestrator execution preparation.
    
    States are grouped into three categories:
    - Preparation states: BACKLOG, QUEUED, PREPARED
    - Execution states: IN_PROGRESS, COMPLETED
    - Terminal states: FAILED, COMPLETED
    """

    BACKLOG = "backlog"
    QUEUED = "queued"
    PREPARED = "prepared"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Project(Base):
    """Initial project table for future multi-project awareness."""

    __tablename__ = "project"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TelegramUser(Base):
    """Persisted Telegram user profile and notification preferences."""

    __tablename__ = "telegram_users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'operator', 'admin')",
            name="telegram_users_role_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    telegram_id: Mapped[int] = mapped_column(BIGINT, nullable=False, unique=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TelegramUserRole.USER.value,
        server_default=TelegramUserRole.USER.value,
    )
    subscribed_events: Mapped[dict[str, bool]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    last_active: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Requirement(Base):
    """Persisted requirement record for intake artifacts.

    Requirements represent the initial intake artifact that may trigger
    one or more planning/execution/analysis tasks.
    """

    __tablename__ = "requirement"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'rejected', 'archived')",
            name="ck_requirement_status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RequirementStatus.DRAFT.value,
        server_default=RequirementStatus.DRAFT.value,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("project.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Task(Base):
    """Persisted task record used by the API and Telegram integration."""

    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint(
            "created_by_type IN ('user', 'agent')",
            name="ck_task_created_by_type_allowed",
        ),
        CheckConstraint(
            "status IN ('backlog', 'queued', 'prepared', 'in_progress', 'completed', 'failed')",
            name="ck_task_status_allowed",
        ),
        CheckConstraint(
            "type IN ('planning', 'execution', 'analysis', 'requirement')",
            name="ck_task_type_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_number: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        nullable=False,
        unique=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TaskStatus.BACKLOG.value,
        server_default=TaskStatus.BACKLOG.value,
    )
    execution_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("project.id"),
        nullable=True,
    )
    requirement_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("requirement.id"),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    # REQ-011: Execution preparation metadata
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    locked_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    preparation_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_preparation_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    branch_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    worktree_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )
    commit_sha_before: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    prepared_context_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    batch_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Deprecated: Use workflow_id instead. Kept for backward compatibility.",
    )
    workflow_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        index=True,
    )
    allow_parallel_execution: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent


class WorktreeStatus(str, Enum):
    """Worktree lifecycle states for REQ-021."""

    ACTIVE = "active"
    CLEANED = "cleaned"
    ERROR = "error"


class WorktreeMetadata(Base):
    """Centralized worktree metadata for REQ-021.

    Tracks the lifecycle of git worktrees created for task execution,
    enabling proper cleanup and preventing resource leaks.
    """

    __tablename__ = "worktree_metadata"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'cleaned', 'error')",
            name="ck_worktree_metadata_status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow.id"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task.id"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,
        comment="Absolute path to the worktree directory",
    )
    branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Git branch name for this worktree",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorktreeStatus.ACTIVE.value,
        server_default=WorktreeStatus.ACTIVE.value,
        comment="Worktree lifecycle state: active, cleaned, error",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Timestamp when worktree was created",
    )
    cleaned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when worktree was cleaned up",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if worktree entered error state",
    )

    def __repr__(self) -> str:
        return (
            f"<WorktreeMetadata(id={self.id}, workflow_id={self.workflow_id}, "
            f"task_id={self.task_id}, path={self.path}, status={self.status})>"
        )

    @property
    def is_active(self) -> bool:
        """Check if worktree is currently active."""
        return self.status == WorktreeStatus.ACTIVE.value

    @property
    def is_cleaned(self) -> bool:
        """Check if worktree has been cleaned up."""
        return self.status == WorktreeStatus.CLEANED.value

    @property
    def is_in_error(self) -> bool:
        """Check if worktree is in error state."""
        return self.status == WorktreeStatus.ERROR.value

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "task_id": str(self.task_id),
            "path": self.path,
            "branch": self.branch,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "cleaned_at": self.cleaned_at.isoformat() if self.cleaned_at else None,
            "error_message": self.error_message,
        }
