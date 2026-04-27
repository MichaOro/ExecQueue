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
    """Supported executable task types.

    Note: 'requirement' is an intake type but NOT an executable task type.
    Requirements are mapped to 'planning' tasks during intake validation.
    """

    PLANNING = "planning"
    EXECUTION = "execution"
    ANALYSIS = "analysis"


class RequirementStatus(str, Enum):
    """Supported requirement lifecycle states."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    """Initial task lifecycle states."""

    BACKLOG = "backlog"


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
            "type IN ('planning', 'execution', 'analysis')",
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
