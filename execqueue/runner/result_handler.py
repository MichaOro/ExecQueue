"""Result handling and workflow status persistence for REQ-016/REQ-017."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from execqueue.db.models import Task, TaskStatus
from execqueue.models.enums import EventDirection, ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent
from execqueue.orchestrator.workflow_repo import WorkflowRepository

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from execqueue.runner.workflow_executor import TaskResult


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ResultHandler:
    """Handles persistence and aggregation of task execution results."""

    def __init__(self, session: Session):
        self._session = session
        self._workflow_repo = WorkflowRepository()

    def persist_results(
        self,
        workflow_id: UUID,
        task_results: list["TaskResult"],
    ) -> None:
        try:
            persisted_any = False

            for result in task_results:
                execution = self._get_execution(result.task_id)
                if not execution:
                    logger.warning(
                        "TaskExecution not found for task %s, skipping persistence",
                        result.task_id,
                    )
                    continue

                if execution.workflow_id is None:
                    execution.workflow_id = workflow_id

                self._update_execution_from_result(execution, result)
                self._log_event(
                    execution=execution,
                    event_type="status_update",
                    data={
                        "status": result.status,
                        "duration_seconds": result.duration_seconds,
                        "error_message": result.error_message,
                    },
                )
                persisted_any = True

            if not persisted_any:
                logger.info("No task results persisted for workflow %s", workflow_id)
                return

            self._session.commit()
            self._workflow_repo.check_and_update_workflow_status(self._session, workflow_id)
            logger.info("Persisted %d results for workflow %s", len(task_results), workflow_id)

        except Exception as exc:
            self._session.rollback()
            logger.error("Failed to persist results: %s", exc, exc_info=True)
            raise

    def aggregate_workflow_status(
        self,
        workflow_id: UUID,
    ) -> str:
        from execqueue.orchestrator.workflow_models import WorkflowStatus

        summary = self._workflow_repo.get_workflow_task_summary(self._session, workflow_id)
        return self._workflow_repo.calculate_workflow_status(summary).value

    def _get_execution(self, task_id: UUID) -> TaskExecution | None:
        return (
            self._session.query(TaskExecution)
            .filter(TaskExecution.task_id == task_id)
            .order_by(TaskExecution.created_at.desc())
            .first()
        )

    def _update_execution_from_result(
        self,
        execution: TaskExecution,
        result: "TaskResult",
    ) -> None:
        if result.status == "DONE":
            execution.status = ExecutionStatus.DONE.value
            execution.finished_at = utcnow()
            self._set_task_status(execution.task_id, TaskStatus.COMPLETED.value)
        elif result.status == "FAILED":
            execution.status = ExecutionStatus.FAILED.value
            execution.finished_at = utcnow()
            self._set_task_status(execution.task_id, TaskStatus.FAILED.value)
        elif result.status == "RETRY":
            execution.status = ExecutionStatus.PREPARED.value
            execution.finished_at = None
            self._set_task_status(execution.task_id, TaskStatus.PREPARED.value)

        if result.commit_sha:
            execution.commit_sha_after = result.commit_sha
        if result.worktree_path:
            execution.worktree_path = result.worktree_path
        if result.opencode_session_id:
            execution.opencode_session_id = result.opencode_session_id
        if result.error_message:
            execution.error_message = result.error_message

        if execution.result_summary is None:
            execution.result_summary = {}
        if result.duration_seconds is not None:
            execution.result_summary["duration_seconds"] = result.duration_seconds
        if result.result_payload is not None:
            execution.result_summary["result_payload"] = result.result_payload
        flag_modified(execution, "result_summary")

        execution.updated_at = utcnow()

    def _set_task_status(self, task_id: UUID, status: str) -> None:
        task = self._session.get(Task, task_id)
        if task is not None:
            task.status = status
            task.updated_at = utcnow()

    def _log_event(
        self,
        execution: TaskExecution,
        event_type: str,
        data: dict | None = None,
    ) -> None:
        latest_sequence = (
            self._session.query(TaskExecutionEvent.sequence)
            .filter(TaskExecutionEvent.task_execution_id == execution.id)
            .order_by(TaskExecutionEvent.sequence.desc())
            .first()
        )
        next_sequence = 1 if latest_sequence is None else latest_sequence[0] + 1

        event = TaskExecutionEvent(
            task_execution_id=execution.id,
            sequence=next_sequence,
            direction=EventDirection.OUTBOUND.value,
            event_type=event_type,
            payload=data or {},
            correlation_id=execution.correlation_id,
        )
        self._session.add(event)
