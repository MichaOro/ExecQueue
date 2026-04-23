from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from execqueue.db.session import get_session
from execqueue.models.task import Task
from execqueue.runtime import is_test_mode

router = APIRouter()


@router.get("/")
def list_tasks(session: Session = Depends(get_session)):
    tasks = session.exec(
        select(Task).where(Task.is_test == is_test_mode())
    ).all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "retry_count": t.retry_count,
            "source_type": t.source_type,
        }
        for t in tasks
    ]


@router.post("/")
def create_task(task: Task, session: Session = Depends(get_session)):
    task.is_test = is_test_mode()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task
