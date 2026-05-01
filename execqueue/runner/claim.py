"""Claim logic for atomic task reservation.

This module implements the core claim logic for REQ-012-02:
- Atomically claim prepared tasks
- Create TaskExecution records
- Ensure no duplicate claims via rowcount verification
- Per REQ-012-10: Structured logging with correlation IDs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from execqueue.db.models import Task, TaskStatus
from execqueue.models.enums import EventType, FINAL_EXECUTION_STATUSES
from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent
from execqueue.observability import (
    generate_correlation_id,
    log_phase_event,
    get_logger,
    record_execution_claimed,
    get_metrics,
)

logger = logging.getLogger(__name__)
obs_logger = get_logger(__name__)


class ClaimFailedError(Exception):
    """Raised when a task claim fails due to concurrent reservation."""

    pass


def claim_task(session: Session, task_id: UUID, runner_id: str) -> TaskExecution:
    """Atomically claim a prepared task and create a TaskExecution.

    This function implements the core claim logic for REQ-012-02:
    1. Checks if an active execution already exists
    2. Atomically updates Task.status from PREPARED to QUEUED
    3. Creates a new TaskExecution with status QUEUED
    4. Emits an EXECUTION_CLAIMED event
    5. Per REQ-012-10: Logs with correlation ID and structured format

    Args:
        session: Database session
        task_id: UUID of the task to claim
        runner_id: Identifier of the runner attempting the claim

    Returns:
        The newly created TaskExecution record

    Raises:
        ClaimFailedError: If the task cannot be claimed (already reserved,
                         not in PREPARED state, or has active execution)
        SQLAlchemyError: If a database error occurs
    """
    task_id_str = str(task_id)
    correlation_id = generate_correlation_id("claim")

    # Check if an active execution already exists
    # Anwendungsebene-Check für frühes Feedback - der Unique Constraint auf
    # Datenbankebene (ix_task_executions_unique_active) ist die endgültige Autorität
    # und verhindert Race Conditions bei gleichzeitigen Claims.
    existing_execution = session.execute(
        select(TaskExecution.id).where(
            and_(
                TaskExecution.task_id == task_id,
                TaskExecution.status.notin_(FINAL_EXECUTION_STATUSES),
            )
        )
    ).scalar()

    if existing_execution:
        log_phase_event(
            obs_logger,
            f"Task {task_id_str} already has an active execution (id={existing_execution})",
            correlation_id=correlation_id,
            task_id=task_id_str,
            runner_id=runner_id,
            phase="claim",
            level=logging.WARNING,
        )
        raise ClaimFailedError(f"Task {task_id_str} already has an active execution")

    # Atomically claim the task using UPDATE with WHERE clause
    # This ensures only one runner can successfully claim a prepared task
    result = session.execute(
        update(Task)
        .where(Task.id == task_id)
        .where(Task.status == TaskStatus.PREPARED.value)
        .values(status=TaskStatus.QUEUED.value)
    )

    if result.rowcount != 1:
        # Task was not in PREPARED state or doesn't exist
        # Check current state for better error message
        task = session.get(Task, task_id)
        if task is None:
            log_phase_event(
                obs_logger,
                f"Task {task_id_str} not found",
                correlation_id=correlation_id,
                task_id=task_id_str,
                runner_id=runner_id,
                phase="claim",
                level=logging.ERROR,
            )
            raise ClaimFailedError(f"Task {task_id_str} not found")
        else:
            log_phase_event(
                obs_logger,
                f"Task {task_id_str} is in status '{task.status}', expected 'prepared'",
                correlation_id=correlation_id,
                task_id=task_id_str,
                runner_id=runner_id,
                phase="claim",
                level=logging.WARNING,
            )
            raise ClaimFailedError(
                f"Task {task_id_str} is in status '{task.status}', cannot be claimed"
            )

    log_phase_event(
        obs_logger,
        f"Successfully claimed task {task_id_str} for runner {runner_id}",
        correlation_id=correlation_id,
        task_id=task_id_str,
        runner_id=runner_id,
        phase="claim",
    )

    task = session.get(Task, task_id)

    # Create the TaskExecution record with correlation ID
    execution = TaskExecution(
        task_id=task_id,
        workflow_id=task.workflow_id if task else None,
        runner_id=runner_id,
        correlation_id=correlation_id,  # REQ-012-10: Correlation ID propagation
        status="queued",
        attempt=1,
        max_attempts=3,
        started_at=datetime.now(timezone.utc),
    )
    session.add(execution)
    session.flush()  # Flush to get the generated ID

    # Emit EXECUTION_CLAIMED event
    now = datetime.now(timezone.utc)
    event = TaskExecutionEvent(
        task_execution_id=execution.id,
        sequence=1,
        correlation_id=correlation_id,  # REQ-012-10: Propagate correlation ID
        event_type=EventType.EXECUTION_CLAIMED.value,
        payload={
            "runner_id": runner_id,
            "claimed_at": now.isoformat(),
        },
        created_at=now,
        direction="outbound",
    )
    session.add(event)

    log_phase_event(
        obs_logger,
        f"Created TaskExecution {execution.id} for task {task_id_str} with status 'queued'",
        correlation_id=correlation_id,
        execution_id=str(execution.id),
        task_id=task_id_str,
        runner_id=runner_id,
        phase="claim",
    )

    # Record metrics
    record_execution_claimed()

    return execution
