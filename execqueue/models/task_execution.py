"""Task Execution model definition.

This module defines the TaskExecution ORM model, representing execution
runs of tasks with detailed runtime information for REQ-012 runner lifecycle.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from execqueue.db.base import Base
from execqueue.models.enums import ExecutionStatus

if TYPE_CHECKING:
    from execqueue.models.task import Task
    from execqueue.models.task_execution_event import TaskExecutionEvent


class TaskExecution(Base):
    """Task execution run record.

    Represents a single execution run of a task, capturing all runtime
    information including branch, worktree, commits, and errors for REQ-012.

    Attributes:
        id: Primary key UUID
        task_id: Foreign key to the executed task
        runner_id: Identifier of the runner that executed the task
        correlation_id: Trace ID across all phases
        prepared_context_version: Version of the prepared context
        opencode_session_id: Session ID from OpenCode
        opencode_message_id: Message/Run ID from OpenCode
        status: Current execution status (REQ-012 granular states)
        started_at: Timestamp when execution started
        dispatched_at: Timestamp when prompt was dispatched
        finished_at: Timestamp when execution finished (if completed)
        heartbeat_at: Last heartbeat timestamp
        attempt: Current attempt number
        max_attempts: Maximum allowed attempts
        error_type: Classified error type
        error_message: Error message if execution failed
        result_summary: JSON summary of execution result
        branch_name: Git branch used for execution
        worktree_path: Path to the worktree
        commit_sha_before: Commit SHA before execution
        commit_sha_after: Commit SHA after execution
        new_commit_shas: Array of new commit SHAs
        changed_files: Array of changed files
        diff_stat: Diff statistics
        has_uncommitted_changes: Whether uncommitted changes exist
        inspection_status: Status of result inspection
        adopted_commit_sha: Commit SHA adopted in target branch
    """

    __tablename__ = "task_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('prepared', 'queued', 'dispatching', 'in_progress', "
            "'result_inspection', 'adopting_commit', 'review', 'done', 'failed')",
            name="ck_task_execution_status_allowed",
        ),
        Index("ix_task_executions_task_id", "task_id"),
        Index("ix_task_executions_status", "status"),
        Index("ix_task_executions_runner_id", "runner_id"),
        Index("ix_task_executions_correlation_id", "correlation_id"),
        Index("ix_task_executions_opencode_session_id", "opencode_session_id"),
        Index("ix_task_executions_updated_at", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("task.id"),
        nullable=False,
    )
    runner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prepared_context_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opencode_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    opencode_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ExecutionStatus.PREPARED.value,
        server_default=ExecutionStatus.PREPARED.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default=text("3"),
    )
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    worktree_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    commit_sha_before: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commit_sha_after: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_commit_shas: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )
    changed_files: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )
    diff_stat: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_uncommitted_changes: Mapped[bool | None] = mapped_column(
        nullable=True,
    )
    inspection_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    adopted_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    task: Mapped["Task"] = relationship(
        "Task",
        lazy="select",
    )

    events: Mapped[list["TaskExecutionEvent"]] = relationship(
        "TaskExecutionEvent",
        back_populates="task_execution",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskExecution(id={self.id}, task_id={self.task_id}, "
            f"status={self.status}, runner_id={self.runner_id!r})>"
        )

    @property
    def is_complete(self) -> bool:
        """Check if the execution has completed (succeeded or failed)."""
        return self.status in ("succeeded", "failed")

    @property
    def is_successful(self) -> bool:
        """Check if the execution succeeded."""
        return self.status in ("succeeded", "done")

    @property
    def is_done(self) -> bool:
        """Check if the execution is in final state."""
        return self.status in ("done", "failed", "review")

    @property
    def is_active(self) -> bool:
        """Check if the execution is still active (not in final state)."""
        return self.status not in ("done", "failed", "review")

    def to_dict(self) -> dict:
        """Convert execution to dictionary representation."""
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "runner_id": self.runner_id,
            "correlation_id": self.correlation_id,
            "prepared_context_version": self.prepared_context_version,
            "opencode_session_id": self.opencode_session_id,
            "opencode_message_id": self.opencode_message_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else None,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "result_summary": self.result_summary,
            "branch_name": self.branch_name,
            "worktree_path": self.worktree_path,
            "commit_sha_before": self.commit_sha_before,
            "commit_sha_after": self.commit_sha_after,
            "new_commit_shas": self.new_commit_shas,
            "changed_files": self.changed_files,
            "diff_stat": self.diff_stat,
            "has_uncommitted_changes": self.has_uncommitted_changes,
            "inspection_status": self.inspection_status,
            "adopted_commit_sha": self.adopted_commit_sha,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
