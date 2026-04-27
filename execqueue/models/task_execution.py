"""Task Execution model definition.

This module defines the TaskExecution ORM model, representing execution
runs of tasks with detailed runtime information.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
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
    information including branch, worktree, commits, and errors.

    Attributes:
        id: Primary key UUID
        task_id: Foreign key to the executed task
        runner_id: Identifier of the runner that executed the task
        status: Current execution status
        started_at: Timestamp when execution started
        finished_at: Timestamp when execution finished (if completed)
        branch_name: Git branch used for execution
        worktree_path: Path to the worktree
        commit_sha_before: Commit SHA before execution
        commit_sha_after: Commit SHA after execution
        error_message: Error message if execution failed
    """

    __tablename__ = "task_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_task_execution_status_allowed",
        ),
        Index("ix_task_executions_task_id", "task_id"),
        Index("ix_task_executions_status", "status"),
        Index("ix_task_executions_runner_id", "runner_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("task.id"),
        nullable=False,
    )
    runner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ExecutionStatus.PENDING.value,
        server_default=ExecutionStatus.PENDING.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    worktree_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    commit_sha_before: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commit_sha_after: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

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
        return self.status == "succeeded"
