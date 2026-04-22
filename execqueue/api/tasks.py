from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from execqueue.db.engine import get_session
from execqueue.models.task import Task
from execqueue.runtime import apply_test_label, is_test_mode

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    source_type: str
    source_id: int
    title: str
    prompt: str
    verification_prompt: str | None = None
    execution_order: int = 0
    max_retries: int = 5


@router.get("/")
def get_tasks(session: Session = Depends(get_session)):
    statement = (
        select(Task)
        .where(Task.is_test == is_test_mode())
        .order_by(Task.execution_order, Task.id)
    )
    return session.exec(statement).all()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, session: Session = Depends(get_session)):
    task = Task(
        source_type=payload.source_type,
        source_id=payload.source_id,
        title=apply_test_label(payload.title),
        prompt=payload.prompt,
        verification_prompt=payload.verification_prompt,
        execution_order=payload.execution_order,
        max_retries=payload.max_retries,
        is_test=is_test_mode(),
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/{task_id}/start")
def start_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "in_progress"
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/{task_id}/done")
def mark_task_done(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "done"
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.post("/{task_id}/fail")
def mark_task_failed(task_id: int, result: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "failed"
    task.last_result = result
    task.retry_count += 1
    session.add(task)
    session.commit()
    session.refresh(task)
    return task
