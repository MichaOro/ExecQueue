"""Execution Plan model definition.

This module defines the ExecutionPlan ORM model, representing execution
plans generated for requirements.
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
from execqueue.models.enums import ExecutionStatus

if TYPE_CHECKING:
    from execqueue.models.task import Task


# Use JSON type that works with both SQLite and PostgreSQL
# For PostgreSQL, JSONB is preferred but JSON also works
from sqlalchemy import JSON
ExecutionPlanContentType = JSON


class ExecutionPlan(Base):
    """Execution plan record for a requirement.

    Execution plans represent the concrete plan generated for executing
    tasks associated with a requirement. They contain the structured
    content that drives the execution process.

    Attributes:
        id: Primary key UUID
        requirement_id: Foreign key to requirement
        created_by_task_id: Foreign key to the task that created this plan
        created_at: Timestamp of creation
        content: JSON blob containing the execution plan
        status: Current status of the execution plan
    """

    __tablename__ = "execution_plan"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_execution_plan_status_allowed",
        ),
        Index("ix_execution_plan_requirement_id", "requirement_id"),
        Index("ix_execution_plan_created_by_task_id", "created_by_task_id"),
        Index("ix_execution_plan_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    requirement_id: Mapped[UUID] = mapped_column(
        ForeignKey("requirement.id"),
        nullable=False,
    )
    created_by_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("task.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        ExecutionPlanContentType(),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ExecutionStatus.PENDING.value,
        server_default=ExecutionStatus.PENDING.value,
    )

    # Relationships
    requirement: Mapped["Requirement"] = relationship(
        "Requirement",
        backref="execution_plans",
         lazy="select",
    )

    # Note: The created_by_task_id foreign key exists but the relationship
    # is not defined here to avoid conflicts with the existing Task model.
    # A full bidirectional relationship would require updating execqueue/db/models.py

    def __repr__(self) -> str:
        return (
            f"<ExecutionPlan(id={self.id}, requirement_id={self.requirement_id}, "
            f"status={self.status})>"
        )
