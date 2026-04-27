"""Home for future tenant-aware domain endpoints.

Domain endpoints stay separate from technical system endpoints such as health
checks. When shared tenant scenarios are introduced, handlers in this router
can read ``X-Tenant-ID`` request-scoped through local FastAPI dependencies on
the concrete endpoint instead of relying on global middleware or app state.
"""

from __future__ import annotations

import logging
from typing import Literal, NoReturn

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from execqueue.api.dependencies import DatabaseSession
from execqueue.tasks import (
    DEFAULT_TASK_MAX_RETRIES,
    TaskNotFoundError,
    create_task_from_requirement,
)
from execqueue.tasks.service import (
    ALLOWED_INTAKE_TYPES,
    IdempotencyError,
    create_task,
    get_task_status,
    validate_task_type,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class TaskCreateRequest(BaseModel):
    """Request payload for task creation.

    Supports intake types: requirement, planning, execution, analysis.
    The 'requirement' type is mapped to 'planning' during validation
    since requirements are not executable task types.

    For requirement type:
    - prompt serves as both requirement description and task prompt
    - A Requirement record is created with DRAFT status
    - A Planning task is created and linked to the requirement
    """

    prompt: str = Field(min_length=1)
    type: str = Field(min_length=1, max_length=32)
    created_by_type: Literal["user", "agent"]
    created_by_ref: str = Field(min_length=1, max_length=255)
    title: str | None = Field(None, min_length=1, max_length=255)
    idempotency_key: str | None = Field(None, min_length=1, max_length=255)


class TaskCreateResponse(BaseModel):
    """Response payload for created tasks."""

    task_number: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class TaskStatusResponse(BaseModel):
    """Response payload for task status lookups."""

    task_number: int
    status: str


class ErrorResponse(BaseModel):
    """Simple error payload contract."""

    detail: str


class ValidationErrorDetail(BaseModel):
    """Structured validation error with field, reason, and expected values."""

    field: str
    reason: str
    expected: str | None = None


class IntakeValidationErrorResponse(BaseModel):
    """Structured validation error response for intake contract violations."""

    detail: str
    errors: list[ValidationErrorDetail]


def _raise_intake_validation_error(
    *,
    field: str,
    reason: str,
    expected: str | None = None,
) -> NoReturn:
    """Raise a structured 422 response for intake contract violations."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "detail": "Intake validation failed",
            "errors": [
                {
                    "field": field,
                    "reason": reason,
                    "expected": expected,
                }
            ],
        },
    )


def _raise_idempotency_conflict(idempotency_key: str) -> NoReturn:
    """Raise a structured 409 response for duplicate idempotency keys."""
    logger.warning("Intake rejected: duplicate idempotency_key=%s", idempotency_key)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Duplicate request: task with idempotency_key '{idempotency_key}' already exists.",
    )


@router.post(
    "/task",
    summary="Create a task",
    operation_id="tasks_create_post",
    tags=["API"],
    status_code=status.HTTP_201_CREATED,
    response_model=TaskCreateResponse,
    responses={
        201: {"description": "Task created successfully"},
        409: {"description": "Duplicate idempotency key"},
        422: {"description": "Invalid task payload"},
    },
)
async def create_task_endpoint(
    payload: TaskCreateRequest,
    session: DatabaseSession,
) -> TaskCreateResponse:
    """Create a new task for later processing.

    Validates the intake contract:
    - Accepts intake types: requirement, planning, execution, analysis
    - For 'requirement': Creates Requirement + Planning task atomically
    - For other types: Creates task directly with matching type
    - Returns structured validation errors for invalid payloads

    Observability:
    - Logs intake start, success, and all error paths
    - Does NOT log sensitive prompt content for privacy
    """
    # Log intake start (without sensitive content)
    logger.info(
        "Intake started: type=%s, created_by_type=%s, created_by_ref=%s",
        payload.type,
        payload.created_by_type,
        payload.created_by_ref,
    )

    # Validate and normalize the task type via service layer
    try:
        persisted_type = validate_task_type(payload.type)
    except ValueError as exc:
        # Log validation error (AP 5: structured rejection)
        logger.warning(
            "Intake rejected: validation failed for type=%s - %s",
            payload.type,
            str(exc),
        )
        _raise_intake_validation_error(
            field="type",
            reason=str(exc),
            expected=", ".join(sorted(ALLOWED_INTAKE_TYPES)),
        )

    # Handle requirement intake: create Requirement + Planning task atomically
    if payload.type == "requirement":
        try:
            requirement, task = create_task_from_requirement(
                session,
                requirement_title=payload.title or "",
                requirement_description=payload.prompt,
                task_prompt=payload.prompt,
                created_by_type=payload.created_by_type,
                created_by_ref=payload.created_by_ref,
                max_retries=DEFAULT_TASK_MAX_RETRIES,
                idempotency_key=payload.idempotency_key,
            )
            # Log success (AP 5: observability without sensitive content)
            logger.info(
                "Intake success: requirement_id=%s, task_number=%s, type=%s",
                requirement.id,
                task.task_number,
                task.type,
            )
        except ValueError as exc:
            logger.warning("Intake rejected: requirement validation failed - %s", exc)
            error_message = str(exc)
            if "title" in error_message.lower():
                _raise_intake_validation_error(
                    field="title",
                    reason=error_message,
                    expected="non-empty string (max 255 chars)",
                )
            _raise_intake_validation_error(
                field="prompt",
                reason=error_message,
                expected="non-empty string",
            )
        except IdempotencyError as exc:
            _raise_idempotency_conflict(exc.idempotency_key)
        except Exception as exc:
            # Log unexpected persistence error (AP 5: distinguishable from validation)
            logger.exception(
                "Intake failed: persistence error for requirement type"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error during task creation",
            ) from exc
    else:
        # Direct task creation for planning, execution, analysis
        try:
            task = create_task(
                session,
                prompt=payload.prompt,
                task_type=persisted_type,
                created_by_type=payload.created_by_type,
                created_by_ref=payload.created_by_ref,
                max_retries=DEFAULT_TASK_MAX_RETRIES,
                idempotency_key=payload.idempotency_key,
            )
            # Log success (AP 5: observability without sensitive content)
            logger.info(
                "Intake success: task_number=%s, type=%s",
                task.task_number,
                task.type,
            )
        except IdempotencyError as exc:
            _raise_idempotency_conflict(exc.idempotency_key)
        except Exception as exc:
            # Log unexpected persistence error (AP 5: distinguishable from validation)
            logger.exception(
                "Intake failed: persistence error for type=%s",
                persisted_type,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error during task creation",
            ) from exc

    return TaskCreateResponse(task_number=task.task_number, status=task.status)


@router.get(
    "/task/{task_number}/status",
    summary="Get task status",
    operation_id="tasks_status_get",
    tags=["API"],
    response_model=TaskStatusResponse,
    responses={
        200: {"description": "Task status returned successfully"},
        404: {"description": "Task not found", "model": ErrorResponse},
    },
)
async def get_task_status_endpoint(
    task_number: int,
    session: DatabaseSession,
) -> TaskStatusResponse:
    """Return the current status for a known public task number."""
    try:
        task_status = get_task_status(session, task_number)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {exc.task_number} not found.",
        ) from exc

    return TaskStatusResponse(
        task_number=task_status.task_number,
        status=task_status.status,
    )
