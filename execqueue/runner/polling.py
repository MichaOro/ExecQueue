"""Polling mechanism for discovering and claiming prepared tasks.

This module implements the polling logic for REQ-012-02:
- Poll for prepared tasks
- Attempt to claim them atomically
- Handle concurrent claim failures gracefully
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from execqueue.db.models import Task, TaskStatus
from execqueue.runner.claim import ClaimFailedError, claim_task
from execqueue.models.task_execution import TaskExecution

logger = logging.getLogger(__name__)


def poll_and_claim_tasks(
    session: Session, runner_id: str, batch_size: int = 1
) -> list[TaskExecution]:
    """Poll for prepared tasks and attempt to claim them.

    This function implements the polling mechanism for REQ-012-02:
    1. Discovers prepared tasks (limited by batch_size)
    2. Attempts to claim each task atomically
    3. Handles claim failures gracefully (task already claimed by another runner)

    Args:
        session: Database session
        runner_id: Identifier of the runner polling for tasks
        batch_size: Maximum number of tasks to claim in one poll cycle

    Returns:
        List of successfully claimed TaskExecution records
    """
    # Discover prepared tasks
    prepared_tasks = session.execute(
        select(Task.id)
        .where(Task.status == TaskStatus.PREPARED.value)
        .limit(batch_size)
    ).scalars().all()

    if not prepared_tasks:
        logger.debug(f"Runner {runner_id}: No prepared tasks found")
        return []

    logger.debug(
        f"Runner {runner_id}: Found {len(prepared_tasks)} prepared task(s)"
    )

    claimed_executions = []
    for task_id in prepared_tasks:
        try:
            execution = claim_task(session, task_id, runner_id)
            claimed_executions.append(execution)
            logger.info(
                f"Runner {runner_id}: Successfully claimed task {task_id} "
                f"(execution {execution.id})"
            )
        except ClaimFailedError as e:
            # Task was claimed by another runner between discovery and claim attempt
            logger.debug(
                f"Runner {runner_id}: Failed to claim task {task_id}: {e}"
            )
            continue

    if claimed_executions:
        logger.info(
            f"Runner {runner_id}: Successfully claimed {len(claimed_executions)} "
            f"task(s) this poll cycle"
        )

    return claimed_executions
