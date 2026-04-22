from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from execqueue.db.engine import get_session
from execqueue.services.queue_service import enqueue_requirement

router = APIRouter(prefix="/queue", tags=["queue"])


class EnqueueRequirementRequest(BaseModel):
    requirement_id: int


@router.post("/enqueue-requirement")
def enqueue_requirement_endpoint(
    payload: EnqueueRequirementRequest,
    session: Session = Depends(get_session),
):
    try:
        tasks = enqueue_requirement(payload.requirement_id, session)
        return {
            "message": "Requirement enqueued",
            "created_task_count": len(tasks),
            "tasks": tasks,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))