"""Workflow repository for REQ-015/REQ-017 persistence."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.orchestrator.idempotency_service import IdempotencyService

if TYPE_CHECKING:
    from execqueue.orchestrator.workflow_models import Workflow, WorkflowContext, WorkflowStatus

logger = logging.getLogger(__name__)


class WorkflowRepository:
    """Repository for Workflow persistence and status aggregation."""

    def __init__(self):
        self.idempotency_service = IdempotencyService()

    def create_workflow(
        self,
        session: Session,
        ctx: "WorkflowContext",
    ) -> "Workflow":
        from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus

        wf = Workflow(
            id=uuid4(),
            epic_id=ctx.epic_id,
            requirement_id=ctx.requirement_id,
            status=WorkflowStatus.RUNNING.value,
        )
        session.add(wf)
        session.flush()
        return wf

    def get_workflow(
        self,
        session: Session,
        workflow_id: UUID,
    ) -> "Workflow | None":
        from execqueue.orchestrator.workflow_models import Workflow

        return session.get(Workflow, workflow_id)

    def update_status(
        self,
        session: Session,
        workflow_id: UUID,
        new_status: "WorkflowStatus",
        error_message: str | None = None,
    ) -> None:
        from execqueue.orchestrator.workflow_models import Workflow

        wf = session.get(Workflow, workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")
        wf.status = new_status.value
        
        # Speichere die Fehlermeldung, falls bereitgestellt
        if error_message is not None:
            wf.error_message = error_message
            
        session.commit()

    def set_runner_uuid(
        self,
        session: Session,
        workflow_id: UUID,
        runner_uuid: str,
    ) -> None:
        from execqueue.orchestrator.workflow_models import Workflow

        wf = session.get(Workflow, workflow_id)
        if wf:
            wf.runner_uuid = runner_uuid
            session.commit()

    def get_running_workflows(
        self,
        session: Session,
    ) -> list["Workflow"]:
        from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus

        stmt = select(Workflow).where(Workflow.status == WorkflowStatus.RUNNING.value)
        return session.execute(stmt).scalars().all()

    def update_workflow(
        self,
        session: Session,
        workflow_id: UUID,
        **kwargs,
    ) -> "Workflow":
        from execqueue.orchestrator.workflow_models import Workflow

        wf = session.get(Workflow, workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        for key, value in kwargs.items():
            if hasattr(wf, key):
                setattr(wf, key, value)

        session.commit()
        return wf

    def get_workflow_task_summary(
        self,
        session: Session,
        workflow_id: UUID,
    ) -> dict[str, int]:
        stmt = (
            select(TaskExecution.status, func.count(TaskExecution.id))
            .where(TaskExecution.workflow_id == workflow_id)
            .group_by(TaskExecution.status)
        )
        return {status: count for status, count in session.execute(stmt).all()}

    def calculate_workflow_status(
        self,
        task_summary: dict[str, int],
    ) -> "WorkflowStatus":
        from execqueue.orchestrator.workflow_models import WorkflowStatus

        if task_summary.get(ExecutionStatus.FAILED.value, 0) > 0:
            return WorkflowStatus.FAILED

        total = sum(task_summary.values())
        if total == 0:
            return WorkflowStatus.RUNNING

        done_count = task_summary.get(ExecutionStatus.DONE.value, 0)
        if done_count == total:
            return WorkflowStatus.DONE

        return WorkflowStatus.RUNNING

    def check_and_update_workflow_status(
        self,
        session: Session,
        workflow_id: UUID,
    ) -> bool:
        from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus

        wf = session.get(Workflow, workflow_id)
        if not wf:
            return False

        if wf.status in (WorkflowStatus.DONE.value, WorkflowStatus.FAILED.value):
            return False

        summary = self.get_workflow_task_summary(session, workflow_id)
        new_status = self.calculate_workflow_status(summary)
        if new_status.value != wf.status:
            logger.info(
                "Updating workflow %s status: %s -> %s",
                workflow_id,
                wf.status,
                new_status.value,
            )
            self.update_status(session, workflow_id, new_status)
            return True

        return False
