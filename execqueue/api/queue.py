from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func
from pydantic import BaseModel
from typing import Optional, List

from execqueue.db.session import get_session
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task
from execqueue.services.queue_service import enqueue_requirement, enqueue_work_package, check_queue_blocked, get_parallel_task_count
from execqueue.services.status_sync_service import (
    update_task_queue_status,
    update_work_package_queue_status,
    update_requirement_queue_status,
    get_kanban_summary,
    VALID_STATUS_TRANSITIONS,
    StatusValidationError,
)
from execqueue.runtime import is_test_mode

router = APIRouter()


class EnqueueRequest(BaseModel):
    requirement_id: int


class QueueStatusUpdate(BaseModel):
    queue_status: str


class BlockQueueUpdate(BaseModel):
    block_queue: bool


class SchedulableUpdate(BaseModel):
    schedulable: bool


class ParallelizationUpdate(BaseModel):
    parallelization_allowed: bool


@router.post("/enqueue-requirement")
def enqueue_requirement_endpoint(request: EnqueueRequest, session: Session = Depends(get_session)):
    try:
        tasks = enqueue_requirement(request.requirement_id, session)
        return {
            "message": "Requirement enqueued",
            "created_task_count": len(tasks),
            "tasks": [{"id": t.id, "title": t.title} for t in tasks],
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/enqueue-work-package/{work_package_id}")
def enqueue_work_package_endpoint(work_package_id: int, session: Session = Depends(get_session)):
    try:
        task = enqueue_work_package(work_package_id, session)
        return {
            "message": "WorkPackage enqueued",
            "task": {"id": task.id, "title": task.title},
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/status")
def get_queue_status(session: Session = Depends(get_session)):
    """
    Get current queue status including blocking and parallel task count.
    """
    is_test_flag = is_test_mode()
    return {
        "queue_blocked": check_queue_blocked(session, is_test_flag),
        "parallel_task_count": get_parallel_task_count(session, is_test_flag),
        "is_test_mode": is_test_flag,
    }


@router.get("/kanban")
def get_kanban_board(session: Session = Depends(get_session)):
    """
    Get Kanban board overview for all entities.
    """
    is_test_flag = is_test_mode()
    summary = get_kanban_summary(session, is_test_flag)
    return summary


@router.patch("/tasks/{task_id}/queue-status")
def update_task_queue_status_endpoint(
    task_id: int,
    request: QueueStatusUpdate,
    session: Session = Depends(get_session)
):
    """
    Update queue_status of a task (Kanban workflow).
    
    Valid transitions:
    - backlog: → in_progress, trash
    - in_progress: → backlog, review, trash
    - review: → in_progress, backlog, done, trash
    - done: → review, backlog
    - trash: → backlog
    """
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    try:
        updated_task = update_task_queue_status(task, request.queue_status, session)
        return {
            "message": "Task queue_status updated",
            "task": {
                "id": updated_task.id,
                "queue_status": updated_task.queue_status,
            },
        }
    except StatusValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/tasks/{task_id}/block-queue")
def update_task_block_queue_endpoint(
    task_id: int,
    request: BlockQueueUpdate,
    session: Session = Depends(get_session)
):
    """
    Toggle block_queue flag for a task.
    """
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.block_queue = request.block_queue
    task.updated_at = task.updated_at
    session.add(task)
    session.commit()
    session.refresh(task)
    
    return {
        "message": f"Queue {'blocked' if request.block_queue else 'unblocked'}",
        "task": {
            "id": task.id,
            "block_queue": task.block_queue,
        },
    }


@router.patch("/tasks/{task_id}/toggle-schedulable")
def update_task_schedulable_endpoint(
    task_id: int,
    request: SchedulableUpdate,
    session: Session = Depends(get_session)
):
    """
    Toggle schedulable flag for a task.
    """
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.schedulable = request.schedulable
    task.updated_at = task.updated_at
    session.add(task)
    session.commit()
    session.refresh(task)
    
    return {
        "message": f"Task {'schedulable' if request.schedulable else 'not schedulable'}",
        "task": {
            "id": task.id,
            "schedulable": task.schedulable,
        },
    }


@router.patch("/tasks/{task_id}/parallelization")
def update_task_parallelization_endpoint(
    task_id: int,
    request: ParallelizationUpdate,
    session: Session = Depends(get_session)
):
    """
    Toggle parallelization_allowed flag for a task.
    """
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.parallelization_allowed = request.parallelization_allowed
    task.updated_at = task.updated_at
    session.add(task)
    session.commit()
    session.refresh(task)
    
    return {
        "message": f"Parallelization {'enabled' if request.parallelization_allowed else 'disabled'}",
        "task": {
            "id": task.id,
            "parallelization_allowed": task.parallelization_allowed,
        },
    }


@router.patch("/work-packages/{wp_id}/queue-status")
def update_work_package_queue_status_endpoint(
    wp_id: int,
    request: QueueStatusUpdate,
    session: Session = Depends(get_session)
):
    """
    Update queue_status of a work package (Kanban workflow).
    """
    wp = session.get(WorkPackage, wp_id)
    if not wp:
        raise HTTPException(status_code=404, detail="WorkPackage not found")
    
    try:
        updated_wp = update_work_package_queue_status(wp, request.queue_status, session)
        return {
            "message": "WorkPackage queue_status updated",
            "work_package": {
                "id": updated_wp.id,
                "queue_status": updated_wp.queue_status,
            },
        }
    except StatusValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/requirements/{req_id}/queue-status")
def update_requirement_queue_status_endpoint(
    req_id: int,
    request: QueueStatusUpdate,
    session: Session = Depends(get_session)
):
    """
    Update queue_status of a requirement (Kanban workflow).
    """
    req = session.get(Requirement, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    
    try:
        updated_req = update_requirement_queue_status(req, request.queue_status, session)
        return {
            "message": "Requirement queue_status updated",
            "requirement": {
                "id": updated_req.id,
                "queue_status": updated_req.queue_status,
            },
        }
    except StatusValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/valid-transitions")
def get_valid_transitions():
    """
    Get all valid Kanban status transitions.
    """
    return {
        "backlog": VALID_STATUS_TRANSITIONS["backlog"],
        "in_progress": VALID_STATUS_TRANSITIONS["in_progress"],
        "review": VALID_STATUS_TRANSITIONS["review"],
        "done": VALID_STATUS_TRANSITIONS["done"],
        "trash": VALID_STATUS_TRANSITIONS["trash"],
    }
