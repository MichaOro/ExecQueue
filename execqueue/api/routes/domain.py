"""Home for future tenant-aware domain endpoints.

Domain endpoints stay separate from technical system endpoints such as health
checks. When shared tenant scenarios are introduced, handlers in this router
can read ``X-Tenant-ID`` request-scoped through local FastAPI dependencies on
the concrete endpoint instead of relying on global middleware or app state.
"""

import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from execqueue.api.dependencies import DatabaseSession
from execqueue.settings import get_settings
from execqueue.tasks import DEFAULT_TASK_MAX_RETRIES, TaskNotFoundError
from execqueue.tasks.service import create_task, get_task_status

router = APIRouter(prefix="/api")

# Path to the global restart script
RESTART_SCRIPT = Path(__file__).parent.parent.parent.parent / "ops" / "scripts" / "global_restart.sh"

# Path to the ACP restart script
ACP_RESTART_SCRIPT = Path(__file__).parent.parent.parent.parent / "ops" / "scripts" / "acp_restart.sh"


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
    "/tasks",
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
    "/tasks/{task_number}/status",
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


@router.post(
    "/system/restart",
    summary="Restart all system services (API and Telegram Bot)",
    operation_id="system_restart_post",
    tags=["System"],
    responses={
        200: {"description": "Restart initiated successfully"},
        403: {"description": "Forbidden - Admin access required"},
        500: {"description": "Restart failed"},
    },
)
async def system_restart() -> dict:
    """Restart all system services (API and Telegram Bot).
    
    Executes the global_restart.sh script which restarts both the API and
    Telegram Bot services. This is an administrative operation.
    
    **Note**: This endpoint should be protected by authentication in production.
    Currently accessible to all callers (MVP).
    
    Returns:
        dict: Status of the restart operation
    """
    settings = get_settings()
    
    # Check if restart script exists
    if not RESTART_SCRIPT.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restart script not found: {RESTART_SCRIPT}",
        )
    
    try:
        # Execute restart script asynchronously (don't wait)
        # We use subprocess.Popen to start the restart in background
        # so the API response is returned immediately
        process = subprocess.Popen(
            [str(RESTART_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        
        # Don't wait for completion - restart happens in background
        # This allows the API to respond before it potentially restarts itself
        
        # Log the restart attempt (to file)
        log_file = Path(__file__).parent.parent.parent.parent / "ops" / "logs" / "api_restart_requests.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, "a") as f:
            f.write(f"[{process.pid}] Restart initiated via API\n")
        
        return {
            "status": "initiated",
            "message": "System restart initiated. API and Telegram Bot will restart.",
            "pid": process.pid,
        }
        
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Restart script not executable. Check permissions.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate restart: {str(exc)}",
        )


@router.post(
    "/system/acp/restart",
    summary="Restart ACP service only",
    operation_id="acp_restart_post",
    tags=["System"],
    responses={
        200: {"description": "ACP restart initiated successfully"},
        403: {"description": "Forbidden - Admin access required"},
        500: {"description": "ACP restart failed"},
    },
)
async def acp_restart() -> dict:
    """Restart the ACP (OpenCode ACP) service only.
    
    Executes the acp_restart.sh script which restarts the ACP service.
    This is an administrative operation that only affects ACP, not the API
    or Telegram Bot.
    
    **Note**: This endpoint should be protected by authentication in production.
    Currently accessible to all callers (MVP).
    
    Returns:
        dict: Status of the ACP restart operation
    """
    settings = get_settings()
    
    # Check if ACP restart script exists
    if not ACP_RESTART_SCRIPT.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ACP restart script not found: {ACP_RESTART_SCRIPT}",
        )
    
    try:
        # Execute restart script asynchronously (don't wait)
        process = subprocess.Popen(
            [str(ACP_RESTART_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        
        # Log the restart attempt (to file)
        log_file = Path(__file__).parent.parent.parent.parent / "ops" / "logs" / "acp_restart_requests.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, "a") as f:
            f.write(f"[{process.pid}] ACP restart initiated via API\n")
        
        return {
            "status": "initiated",
            "message": "ACP restart initiated. ACP service will restart.",
            "pid": process.pid,
        }
        
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACP restart script not executable. Check permissions.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate ACP restart: {str(exc)}",
        )
