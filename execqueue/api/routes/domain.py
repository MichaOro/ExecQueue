"""Home for future tenant-aware domain endpoints.

Domain endpoints stay separate from technical system endpoints such as health
checks. When shared tenant scenarios are introduced, handlers in this router
can read ``X-Tenant-ID`` request-scoped through local FastAPI dependencies on
the concrete endpoint instead of relying on global middleware or app state.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from execqueue.api.dependencies import DatabaseSession
from execqueue.tasks import DEFAULT_TASK_MAX_RETRIES, TaskNotFoundError
from execqueue.tasks.service import create_task, get_task_status

router = APIRouter(prefix="/api")


class TaskCreateRequest(BaseModel):
    """Request payload for task creation."""

    prompt: str = Field(min_length=1)
    type: Literal["task", "requirement"]
    created_by_type: Literal["user", "agent"]
    created_by_ref: str = Field(min_length=1, max_length=255)


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


@router.post(
    "/task",
    summary="Create a task",
    operation_id="tasks_create_post",
    tags=["API"],
    status_code=status.HTTP_201_CREATED,
    response_model=TaskCreateResponse,
    responses={
        201: {"description": "Task created successfully"},
        422: {"description": "Invalid task payload"},
    },
)
async def create_task_endpoint(
    payload: TaskCreateRequest,
    session: DatabaseSession,
) -> TaskCreateResponse:
    """Create a new task for later processing."""
    task = create_task(
        session,
        prompt=payload.prompt,
        task_type=payload.type,
        created_by_type=payload.created_by_type,
        created_by_ref=payload.created_by_ref,
        max_retries=DEFAULT_TASK_MAX_RETRIES,
    )
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
