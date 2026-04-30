"""Task Execution Event model definition.

This module defines the TaskExecutionEvent ORM model, representing events
generated during task execution for REQ-012 runner lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
    execution-related events for REQ-012 runner lifecycle.

    Attributes:
        id: Primary key UUID
        task_execution_id: Foreign key to the task execution
        sequence: Monotonically increasing sequence number
        external_event_id: External event ID for deduplication
        direction: Event direction (inbound or outbound)
        event_type: Type of event (REQ-012 event types)
        payload: JSON blob containing event-specific data
        correlation_id: Trace ID across all phases
        created_at: Timestamp of event creation
    """

    __tablename__ = "task_execution_events"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name="ck_task_execution_events_direction_allowed",
        ),
        CheckConstraint(
            "event_type IN ('started', 'progress', 'completed', 'error', 'status_update', "
            "'execution.claimed', 'execution.dispatched', 'execution.started', "
            "'execution.completed', 'execution.failed', 'session.created', 'session.closed', "
            "'message.sent', 'message.received', 'stream.connected', 'stream.disconnected', "
            "'stream.heartbeat', 'result.inspected', 'commit.adoption_started', "
            "'commit.adoption_success', 'commit.adoption_conflict', 'retry.scheduled', "
            "'retry.exhausted')",
            name="ck_task_execution_events_event_type_allowed",
        ),
        # Unique Constraint für Event-Deduplizierung (Paket 01)
        Index("ix_task_execution_events_unique_sequence", "task_execution_id", "sequence", unique=True),
        Index("ix_task_execution_events_unique_external_id", "task_execution_id", "external_event_id", unique=True, postgresql_where=text("external_event_id IS NOT NULL")),
        Index("ix_task_execution_events_task_execution_id", "task_execution_id"),
        Index("ix_task_execution_events_direction", "direction"),
        Index("ix_task_execution_events_event_type", "event_type"),
        Index("ix_task_execution_events_created_at", "created_at"),
        Index("ix_task_execution_events_sequence", "task_execution_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("task_executions.id"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    external_event_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    direction: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        EventPayloadType(),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
            "sequence": self.sequence,
            "external_event_id": self.external_event_id,
            "direction": self.direction,
            "event_type": self.event_type,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
