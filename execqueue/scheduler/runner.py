from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from execqueue.models.requirement import Requirement
from execqueue.models.task import Task
from execqueue.models.work_package import WorkPackage
from execqueue.validation.task_validator import validate_task_result
from execqueue.workers.opencode_adapter import execute_with_opencode


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_next_queued_task(session: Session) -> Optional[Task]:
    statement = (
        select(Task)
        .where(Task.status == "queued")
        .order_by(Task.execution_order, Task.id)
    )
    return session.exec(statement).first()


def _mark_task_in_progress(task: Task, session: Session) -> Task:
    task.status = "in_progress"
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _mark_task_done(task: Task, result_text: str, session: Session) -> Task:
    task.status = "done"
    task.last_result = result_text
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _requeue_or_fail_task(task: Task, result_text: str, session: Session) -> Task:
    task.retry_count += 1
    task.last_result = result_text
    task.updated_at = utcnow()

    if task.retry_count >= task.max_retries:
        task.status = "failed"
    else:
        task.status = "queued"

    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _mark_source_done(task: Task, session: Session) -> None:
    if task.source_type == "work_package":
        work_package = session.get(WorkPackage, task.source_id)
        if work_package:
            work_package.status = "done"
            work_package.updated_at = utcnow()
            session.add(work_package)
            session.commit()

            # Optional: if all work packages of the requirement are done, mark requirement done.
            requirement = session.get(Requirement, work_package.requirement_id)
            if requirement:
                remaining = session.exec(
                    select(WorkPackage).where(
                        WorkPackage.requirement_id == requirement.id,
                        WorkPackage.status != "done",
                    )
                ).all()

                if not remaining:
                    requirement.status = "done"
                    requirement.updated_at = utcnow()
                    session.add(requirement)
                    session.commit()

    elif task.source_type == "requirement":
        requirement = session.get(Requirement, task.source_id)
        if requirement:
            requirement.status = "done"
            requirement.updated_at = utcnow()
            session.add(requirement)
            session.commit()


def run_task(task_id: int, session: Session) -> Task:
    task = session.get(Task, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    if task.status != "queued":
        raise ValueError(f"Task {task_id} is not queued")

    task = _mark_task_in_progress(task, session)

    execution_result = execute_with_opencode(
        prompt=task.prompt,
        verification_prompt=task.verification_prompt,
    )

    validation = validate_task_result(execution_result.raw_output)

    if validation.is_done:
        task = _mark_task_done(task, execution_result.raw_output, session)
        _mark_source_done(task, session)
        return task

    return _requeue_or_fail_task(task, execution_result.raw_output, session)


def run_next_task(session: Session) -> Optional[Task]:
    task = get_next_queued_task(session)
    if not task:
        return None
    return run_task(task.id, session)