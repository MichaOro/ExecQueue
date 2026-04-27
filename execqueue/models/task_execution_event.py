"""Task Execution Event model definition.

This module defines the TaskExecutionEvent ORM model, representing events
generated during task execution.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from execqueue.db.base import Base

if TYPE_CHECKING:
    from execqueue.models.task_execution import TaskExecution


# Use JSON type that works with both SQLite and PostgreSQL
from sqlalchemy import JSON
EventPayloadType = JSON


class TaskExecutionEvent(Base):
    """Task execution event record.

    Represents an event generated during task execution, capturing
    inbound or outbound communications, status updates, and other
    execution-related events.

    Attributes:
        id: Primary key UUID
        task_execution_id: Foreign key to the task execution
        direction: Event direction (inbound or outbound)
        event_type: Type of event (started, progress, completed, error, status_update)
        payload: JSON blob containing event-specific data
        created_at: Timestamp of event creation
    """

    __tablename__ = "task_execution_events"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name="ck_task_execution_events_direction_allowed",
        ),
        CheckConstraint(
            "event_type IN ('started', 'progress', 'completed', 'error', 'status_update')",
            name="ck_task_execution_events_event_type_allowed",
        ),
        Index("ix_task_execution_events_task_execution_id", "task_execution_id"),
        Index("ix_task_execution_events_direction", "direction"),
        Index("ix_task_execution_events_event_type", "event_type"),
        Index("ix_task_execution_events_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    task_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("task_executions.id"),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        EventPayloadType(),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    task_execution: Mapped["TaskExecution"] = relationship(
        "TaskExecution",
        back_populates="events",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskExecutionEvent(id={self.id}, task_execution_id={self.task_execution_id}, "
            f"direction={self.direction}, event_type={self.event_type})>"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary representation."""
        return {
            "id": str(self.id),
            "task_execution_id": str(self.task_execution_id),
            "direction": self.direction,
            "event_type": self.event_type,
            "payload": self.payload,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
