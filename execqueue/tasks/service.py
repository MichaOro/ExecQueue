"""Task persistence services."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from execqueue.db.models import Requirement, RequirementStatus, Task
logger = logging.getLogger(__name__)

DEFAULT_TASK_MAX_RETRIES = 3

# Executable task types that can be persisted to the database
ALLOWED_TASK_TYPES = frozenset({"planning", "execution", "analysis", "requirement"})

# Intake types that can be submitted via the API
ALLOWED_INTAKE_TYPES = frozenset({"requirement", "planning", "execution", "analysis"})


class IdempotencyError(Exception):
    """Raised when an idempotency key conflict is detected."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"A task with idempotency_key '{idempotency_key}' already exists."
        )
        self.idempotency_key = idempotency_key


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


def validate_task_type(task_type: str) -> str:
    """Validate and normalize task type for persistence.

    Args:
        task_type: The intake type from the request.

    Returns:
        The normalized task type suitable for persistence.

    Raises:
        ValueError: If the type is not in the allowed intake types.
    """
    if task_type not in ALLOWED_INTAKE_TYPES:
        raise ValueError(
            f"Invalid task type '{task_type}'. "
            f"Allowed intake types: {', '.join(sorted(ALLOWED_INTAKE_TYPES))}"
        )

    # Map 'requirement' intake to 'requirement' task type (not planning anymore)
    if task_type == "requirement":
        return "requirement"

    return task_type


def create_task(
    session: Session,
    *,
    prompt: str,
    task_type: str,
    created_by_type: str,
    created_by_ref: str,
    max_retries: int = DEFAULT_TASK_MAX_RETRIES,
    requirement_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> Task:
    """Create a task row and return the persisted ORM object.

    Note on Idempotency:
        - If idempotency_key is None, the task is created without deduplication.
        - If idempotency_key is provided and already exists, IdempotencyError is raised.
        - Multiple tasks WITHOUT an idempotency_key are allowed (NULL is not unique).

    Args:
        session: SQLAlchemy session.
        prompt: The task prompt/description.
        task_type: The task type (will be validated and normalized).
        created_by_type: Who created the task (user or agent).
        created_by_ref: Reference identifier for the creator.
        max_retries: Maximum retry attempts.
        requirement_id: Optional UUID of the linked requirement.
        idempotency_key: Optional unique key for deduplication.

    Returns:
        The persisted Task instance.

    Raises:
        ValueError: If task_type is invalid.
        IdempotencyError: If the idempotency_key already exists.
    """
    # Validate and normalize the task type
    normalized_type = validate_task_type(task_type)
    logger.info(
        "Task creation started: type=%s, created_by_type=%s, created_by_ref=%s, requirement_id=%s, has_idempotency_key=%s",
        normalized_type,
        created_by_type,
        created_by_ref,
        requirement_id,
        idempotency_key is not None,
    )

    task = Task(
        prompt=prompt,
        type=normalized_type,
        max_retries=max_retries,
        created_by_type=created_by_type,
        created_by_ref=created_by_ref,
        requirement_id=requirement_id,
        idempotency_key=idempotency_key,
    )

    if _requires_task_number_fallback(session):
        task.task_number = _allocate_sqlite_task_number(session)

    session.add(task)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # Check if this is an idempotency key conflict
        if idempotency_key:
            logger.warning(
                "Task creation rejected: duplicate idempotency_key=%s",
                idempotency_key,
            )
            raise IdempotencyError(idempotency_key) from exc
        raise

    session.refresh(task)
    logger.info(
        "Task creation committed: task_number=%s, type=%s, requirement_id=%s",
        task.task_number,
        task.type,
        task.requirement_id,
    )

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


def create_requirement(
    session: Session,
    *,
    title: str,
    description: str,
    status: str = "draft",
    project_id: UUID | None = None,
) -> Requirement:
    """Create a requirement row and return the persisted ORM object.

    Args:
        session: SQLAlchemy session.
        title: The requirement title (non-empty, max 255 chars).
        description: The requirement description (non-empty).
        status: The requirement status (draft, approved, rejected, archived).
        project_id: Optional UUID of the linked project.

    Returns:
        The persisted Requirement instance.

    Raises:
        ValueError: If status is invalid or title/description is empty.
    """
    normalized_title = title.strip() if title else ""
    normalized_description = description.strip() if description else ""

    # Validate required fields
    if not normalized_title:
        raise ValueError("Requirement title must not be empty")
    if len(normalized_title) > 255:
        raise ValueError("Requirement title must not exceed 255 characters")
    if not normalized_description:
        raise ValueError("Requirement description must not be empty")

    allowed_statuses = {"draft", "approved", "rejected", "archived"}
    if status not in allowed_statuses:
        raise ValueError(
            f"Invalid requirement status '{status}'. "
            f"Allowed statuses: {', '.join(sorted(allowed_statuses))}"
        )

    requirement = Requirement(
        title=normalized_title,
        description=normalized_description,
        status=status,
        project_id=project_id,
    )

    session.add(requirement)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise

    session.refresh(requirement)
    return requirement


def create_task_from_requirement(
    session: Session,
    *,
    requirement_title: str,
    requirement_description: str,
    task_prompt: str,
    created_by_type: str,
    created_by_ref: str,
    max_retries: int = DEFAULT_TASK_MAX_RETRIES,
    idempotency_key: str | None = None,
) -> tuple[Requirement, Task]:
    """Atomically create a requirement and its initial planning task.

    This function implements the requirement intake flow from REQ-009:
    - Creates a Requirement record with DRAFT status
    - Creates exactly one Planning task linked to the requirement
    - Both operations succeed or fail together in a single transaction

    Args:
        session: SQLAlchemy session.
        requirement_title: The requirement title (non-empty, max 255 chars).
        requirement_description: The requirement description (non-empty).
        task_prompt: The task prompt (may differ from description).
        created_by_type: Who created the task (user or agent).
        created_by_ref: Reference identifier for the creator.
        max_retries: Maximum retry attempts for the task.
        idempotency_key: Optional unique key for task deduplication.

    Returns:
        A tuple of (Requirement, Task) instances.

    Raises:
        ValueError: If requirement title/description is invalid.
        IdempotencyError: If the idempotency_key already exists.
    """
    normalized_title = requirement_title.strip() if requirement_title else ""
    normalized_description = (
        requirement_description.strip() if requirement_description else ""
    )
    logger.info(
        "Requirement intake started: created_by_type=%s, created_by_ref=%s, has_idempotency_key=%s",
        created_by_type,
        created_by_ref,
        idempotency_key is not None,
    )

    # Validate requirement fields (reuse create_requirement validation logic)
    if not normalized_title:
        raise ValueError("Requirement title must not be empty")
    if len(normalized_title) > 255:
        raise ValueError("Requirement title must not exceed 255 characters")
    if not normalized_description:
        raise ValueError("Requirement description must not be empty")

    # Create requirement
    requirement = Requirement(
        title=normalized_title,
        description=normalized_description,
        status=RequirementStatus.DRAFT.value,
    )
    session.add(requirement)

    # Flush to get the requirement ID before committing
    session.flush()

    # Create planning task linked to the requirement
    task = Task(
        prompt=task_prompt,
        type="planning",
        max_retries=max_retries,
        created_by_type=created_by_type,
        created_by_ref=created_by_ref,
        requirement_id=requirement.id,
        idempotency_key=idempotency_key,
    )

    if _requires_task_number_fallback(session):
        task.task_number = _allocate_sqlite_task_number(session)

    session.add(task)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if idempotency_key:
            logger.warning(
                "Requirement intake rejected: duplicate idempotency_key=%s",
                idempotency_key,
            )
            raise IdempotencyError(idempotency_key) from exc
        raise

    session.refresh(requirement)
    session.refresh(task)
    logger.info(
        "Requirement intake committed: requirement_id=%s, task_number=%s, type=%s",
        requirement.id,
        task.task_number,
        task.type,
    )

    return requirement, task
