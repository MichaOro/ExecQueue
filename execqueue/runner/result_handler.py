"""Result handling and persistence for REQ-016."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from execqueue.db.models import TaskExecution, TaskExecutionEvent
    from execqueue.runner.workflow_executor import TaskResult

logger = logging.getLogger(__name__)


class ResultHandler:
    """Handles persistence and aggregation of task results.

    Usage:
        async with get_db_session() as session:
            handler = ResultHandler(session)
            handler.persist_results(workflow_id, task_results)
            workflow_status = handler.aggregate_workflow_status(workflow_id)
    """

    def __init__(self, session: Session):
        """Initialize result handler.

        Args:
            session: Database session for persistence (must be managed by caller)
        """
        self._session = session

    def persist_results(
        self,
        workflow_id: UUID,
        task_results: list["TaskResult"],
    ) -> None:
        """Persist task results to database.

        Args:
            workflow_id: Workflow identifier
            task_results: List of TaskResult to persist

        Note:
            All results are persisted in a single transaction.
            If any result fails to persist, the entire transaction is rolled back.
        """
        try:
            for result in task_results:
                # Get existing TaskExecution (created by Orchestrator)
                execution = self._get_execution(result.task_id)
                if not execution:
                    logger.warning(
                        f"TaskExecution not found for task {result.task_id}, "
                        f"skipping persistence"
                    )
                    continue

                # Update execution with result data
                self._update_execution_from_result(execution, result)

                # Log event for this result
                self._log_event(
                    execution=execution,
                    event_type="task_result",
                    data={
                        "status": result.status,
                        "duration_seconds": result.duration_seconds,
                        "error_message": result.error_message,
                    },
                )

                logger.info(
                    f"Persisted result for task {result.task_id}: "
                    f"status={result.status}, "
                    f"commit_sha={result.commit_sha}"
                )

            # Commit all changes atomically
            self._session.commit()
            logger.info(f"Persisted {len(task_results)} results for workflow {workflow_id}")

        except Exception as e:
            # Rollback on error
            self._session.rollback()
            logger.error(f"Failed to persist results: {e}", exc_info=True)
            raise

    def aggregate_workflow_status(
        self,
        workflow_id: UUID,
    ) -> str:
        """Aggregate task results to determine workflow status.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Workflow status: 'running', 'done', or 'failed'
        """
        from execqueue.orchestrator.workflow_models import WorkflowStatus
        from execqueue.db.models import TaskExecution

        # Get all TaskExecutions for this workflow
        executions = self._session.query(TaskExecution).filter(
            TaskExecution.workflow_id == workflow_id
        ).all()

        if not executions:
            logger.warning(f"No TaskExecutions found for workflow {workflow_id}")
            return WorkflowStatus.DONE.value  # Empty workflow

        # Check execution statuses
        done_count = sum(1 for e in executions if e.status == "done")
        failed_count = sum(1 for e in executions if e.status == "failed")

        if failed_count > 0:
            return WorkflowStatus.FAILED.value
        elif done_count == len(executions):
            return WorkflowStatus.DONE.value
        else:
            return WorkflowStatus.RUNNING.value

    def _get_execution(self, task_id: UUID) -> "TaskExecution | None":
        """Get existing TaskExecution for a task.

        Args:
            task_id: Task identifier

        Returns:
            TaskExecution or None if not found

        Note:
            TaskExecution should have been created by Orchestrator before execution.
        """
        from execqueue.db.models import TaskExecution

        return (
            self._session.query(TaskExecution)
            .filter(TaskExecution.task_id == task_id)
            .first()
        )

    def _update_execution_from_result(
        self,
        execution: "TaskExecution",
        result: "TaskResult",
    ) -> None:
        """Update TaskExecution from TaskResult.

        Args:
            execution: TaskExecution to update
            result: TaskResult with new data
        """
        # Map status
        if result.status == "DONE":
            execution.status = "done"
        elif result.status == "FAILED":
            execution.status = "failed"
        elif result.status == "RETRY":
            execution.status = "prepared"  # Reset for retry

        # Update commit SHA
        if result.commit_sha:
            execution.commit_sha_after = result.commit_sha

        # Update worktree path
        if result.worktree_path:
            execution.worktree_path = result.worktree_path

        # Update session ID
        if result.opencode_session_id:
            execution.opencode_session_id = result.opencode_session_id

        # Update error message
        if result.error_message:
            execution.error_message = result.error_message

        # Update duration
        if result.duration_seconds:
            # Store as part of result_summary JSON
            if execution.result_summary is None:
                execution.result_summary = {}
            execution.result_summary["duration_seconds"] = result.duration_seconds

        execution.updated_at = datetime.utcnow()

    def _log_event(
        self,
        execution: "TaskExecution",
        event_type: str,
        data: dict | None = None,
    ) -> None:
        """Log a TaskExecutionEvent.

        Args:
            execution: Related TaskExecution
            event_type: Event type string
            data: Optional event data (JSON)
        """
        from execqueue.db.models import TaskExecutionEvent

        event = TaskExecutionEvent(
            task_execution_id=execution.id,
            event_type=event_type,
            data=data or {},
        )
        self._session.add(event)
