"""Orchestrator trigger adapter for task intake.

This module provides a minimal trigger mechanism that fires after successful
task persistence. It is designed to be non-blocking and fault-tolerant:
trigger failures must never undo a successfully persisted task.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

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

    Active implementation (REQ-011):
    - Starts the orchestrator synchronously to process backlog tasks
    - Runs one preparation cycle (backlog -> prepared)
    - Logs all preparation events for observability

    Args:
        session: SQLAlchemy session (used for orchestrator DB access).
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

        # Import orchestrator here to avoid circular imports
        from execqueue.orchestrator.main import Orchestrator

        # Generate unique worker ID for this trigger invocation
        worker_id = f"worker-{os.getpid()}-thread-{threading.get_ident()}"

        logger.info("Starting orchestrator preparation cycle (worker=%s)", worker_id)

        # Create orchestrator instance with defaults
        # Note: Worktree root and base repo path should be configurable in production
        orchestrator = Orchestrator(
            worker_id=worker_id,
            max_batch_size=10,
            worktree_root=Path("/tmp/execqueue/worktrees"),
            base_repo_path=Path("."),
        )

        # Run preparation cycle (synchronous, blocking)
        # This processes all backlog tasks and prepares them for execution
        results = orchestrator.run_preparation_cycle(session)

        # Log summary of preparation results
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count

        if results:
            logger.info(
                "Orchestrator preparation cycle completed: %d succeeded, %d failed",
                success_count, failed_count
            )

            # Log individual task results
            for result in results:
                if result.success:
                    logger.info(
                        "Task %s: prepared (runner_mode=%s)",
                        result.task_number,
                        result.context.runner_mode.value if result.context else "unknown"
                    )
                else:
                    logger.error(
                        "Task %s: preparation failed - %s (type=%s)",
                        result.task_number,
                        result.error.message if result.error else "unknown error",
                        result.error.error_type.value if result.error else "unknown"
                    )
        else:
            logger.info("Orchestrator preparation cycle completed: no tasks processed")

        return True

    except Exception as exc:  # pylint: disable=broad-except
        # Log the error but do NOT raise - task is already persisted
        # The orchestrator may have partially processed tasks, but they are safe
        logger.error(
            "Orchestrator trigger failed for task %s: %s. Task remains in current state.",
            task.task_number,
            exc,
            exc_info=True
        )
        return False
