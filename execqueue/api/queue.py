from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from execqueue.db.session import get_session
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.services.queue_service import enqueue_requirement
from execqueue.runtime import is_test_mode

router = APIRouter()


class EnqueueRequest(BaseModel):
    requirement_id: int


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
