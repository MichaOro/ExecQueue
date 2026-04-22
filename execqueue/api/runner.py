from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from execqueue.db.engine import get_session
from execqueue.scheduler.runner import run_next_task

router = APIRouter(prefix="/runner", tags=["runner"])


@router.post("/run-next")
def run_next(session: Session = Depends(get_session)):
    task = run_next_task(session)

    if task is None:
        return {
            "message": "No queued task available"
        }

    return {
        "message": "Task processed",
        "task_id": task.id,
        "status": task.status,
        "retry_count": task.retry_count,
        "source_type": task.source_type,
        "source_id": task.source_id,
    }