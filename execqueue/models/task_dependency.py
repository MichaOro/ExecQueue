"""Task Dependency model definition.

This module defines the TaskDependency ORM model, representing dependencies
between tasks in the execution pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from execqueue.db.base import Base

if TYPE_CHECKING:
    from execqueue.models.task import Task


class TaskDependency(Base):
    """Task dependency record.

    Represents a dependency relationship where one task depends on another
    task completing before it can start.

    Attributes:
        task_id: Foreign key to the task that has the dependency
        depends_on_task_id: Foreign key to the task that must complete first
        created_at: Timestamp of creation

    Note:
        The primary key is a composite of (task_id, depends_on_task_id)
        to ensure uniqueness of dependency relationships.
    """

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies"),
        Index("ix_task_dependencies_task_id", "task_id"),
        Index("ix_task_dependencies_depends_on_task_id", "depends_on_task_id"),
    )

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("task.id"),
        primary_key=True,
    )
    depends_on_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("task.id"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    task: Mapped["Task"] = relationship(
        "Task",
        foreign_keys=[task_id],
        lazy="select",
    )

    depends_on_task: Mapped["Task"] = relationship(
        "Task",
        foreign_keys=[depends_on_task_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskDependency(task_id={self.task_id}, "
            f"depends_on_task_id={self.depends_on_task_id})>"
        )
