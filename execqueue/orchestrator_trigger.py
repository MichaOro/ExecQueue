"""Orchestrator trigger adapter for task intake.

This module provides a minimal trigger mechanism that fires after successful
task persistence. It is designed to be non-blocking and fault-tolerant:
trigger failures must never undo a successfully persisted task.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from execqueue.db.models import Task

logger = logging.getLogger(__name__)


def trigger_orchestrator(session: Session, task: Task) -> bool:
    """Trigger the orchestrator to process a newly created task.

    This function implements the minimal trigger mechanism specified in AP 4:
    - Fires after successful task persistence (DB commit completed)
    - Non-blocking: failures are logged but do not affect the task
    - Idempotent-safe: multiple triggers for the same task are harmless
    - Independent of task type: fires for planning, execution, analysis

    Current implementation:
    - Logs the trigger event for observability
    - Placeholder for future async/event-driven orchestration

    Args:
        session: SQLAlchemy session (used for future extensions).
        task: The persisted task that should trigger orchestration.

    Returns:
        True if trigger succeeded, False if it failed (but task is safe).
    """
    try:
        # Log the trigger event for observability (AP 4 requirement)
        logger.info(
            "Orchestrator triggered for task %s (type=%s, status=%s, requirement_id=%s)",
            task.task_number,
            task.type,
            task.status,
            task.requirement_id,
        )

        # Placeholder for future integration:
        # - Async event publishing (e.g., to a message queue)
        # - HTTP call to orchestrator endpoint
        # - Database polling flag for worker discovery
        #
        # Example future implementation:
        # await orchestrator_client.schedule_task(task.id)
        # event_bus.publish("task.created", {"task_id": task.id})
        # session.execute(update(Task).where(Task.id == task.id).values(triggered=True))

        return True

    except Exception as exc:  # pylint: disable=broad-except
        # Log the error but do NOT raise - task is already persisted
        logger.warning(
            "Orchestrator trigger failed for task %s: %s. Task remains in backlog.",
            task.task_number,
            exc,
        )
        return False
