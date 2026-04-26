"""Task persistence services."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from execqueue.db.models import Task

DEFAULT_TASK_MAX_RETRIES = 3


class TaskNotFoundError(LookupError):
    """Raised when a task cannot be found by its public task number."""

    def __init__(self, task_number: int) -> None:
        super().__init__(f"Task {task_number} was not found.")
        self.task_number = task_number


@dataclass(frozen=True)
class TaskStatusView:
    """Read model for the public task status endpoint."""

    task_number: int
    status: str


def create_task(
    session: Session,
    *,
    prompt: str,
    task_type: str,
    created_by_type: str,
    created_by_ref: str,
    max_retries: int = DEFAULT_TASK_MAX_RETRIES,
) -> Task:
    """Create a task row and return the persisted ORM object."""
    task = Task(
        prompt=prompt,
        type=task_type,
        max_retries=max_retries,
        created_by_type=created_by_type,
        created_by_ref=created_by_ref,
    )

    if _requires_task_number_fallback(session):
        task.task_number = _allocate_sqlite_task_number(session)

    session.add(task)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise

    session.refresh(task)
    return task


def get_task_status(session: Session, task_number: int) -> TaskStatusView:
    """Return the public status view for a known task number."""
    task = session.execute(
        select(Task).where(Task.task_number == task_number)
    ).scalar_one_or_none()

    if task is None:
        raise TaskNotFoundError(task_number)

    return TaskStatusView(task_number=task.task_number, status=task.status)


def _requires_task_number_fallback(session: Session) -> bool:
    """Detect dialects that cannot populate the non-PK identity column for tests."""
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "sqlite"


def _allocate_sqlite_task_number(session: Session) -> int:
    """Allocate task numbers for SQLite-only test runs.

    PostgreSQL remains the production source of truth via the DB identity column.
    """
    max_task_number = session.execute(select(func.max(Task.task_number))).scalar_one()
    return 1 if max_task_number is None else max_task_number + 1
