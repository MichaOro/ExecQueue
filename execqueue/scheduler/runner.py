from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlmodel import Session, select, or_, and_

from execqueue.models.requirement import Requirement
from execqueue.models.task import Task
from execqueue.models.work_package import WorkPackage
from execqueue.models.dead_letter import DeadLetterQueue
from execqueue.runtime import (
    is_test_mode,
    get_scheduler_backoff_multiplier,
    get_scheduler_backoff_min_delay,
    get_scheduler_backoff_max_delay,
    get_worker_instance_id,
    get_worker_lock_timeout_seconds,
    get_opencode_session_timeout,
)
from execqueue.validation.task_validator import validate_task_result
from execqueue.workers.opencode_adapter import execute_with_opencode, OpenCodeACPClient
from execqueue.services.opencode_session_service import OpenCodeSessionService
from execqueue.api import metrics

logger = logging.getLogger(__name__)

# Global worker instance ID
WORKER_INSTANCE_ID = get_worker_instance_id()

# Global ACP client and session service (lazy initialization)
_acp_client: OpenCodeACPClient | None = None
_session_service: OpenCodeSessionService | None = None


def _get_session_service() -> OpenCodeSessionService:
    """Get or create session service (singleton pattern)."""
    global _acp_client, _session_service
    
    if _session_service is None:
        _acp_client = OpenCodeACPClient()
        _session_service = OpenCodeSessionService(acp_client=_acp_client)
    
    return _session_service


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _commit_and_refresh(session: Session, *objects) -> None:
    """Commit session and refresh all objects."""
    for obj in objects:
        session.add(obj)
    session.commit()
    for obj in objects:
        session.refresh(obj)


def _calculate_backoff_delay(retry_count: int) -> float:
    """Calculate exponential backoff delay.
    
    Formula: delay = min(MIN_DELAY * (MULTIPLIER ** retry_count), MAX_DELAY)
    
    Args:
        retry_count: Number of previous retries
        
    Returns:
        Delay in seconds
    """
    multiplier = get_scheduler_backoff_multiplier()
    min_delay = get_scheduler_backoff_min_delay()
    max_delay = get_scheduler_backoff_max_delay()
    
    delay = min_delay * (multiplier ** retry_count)
    return min(delay, max_delay)


def get_next_queued_task(session: Session) -> Optional[Task]:
    """
    Get next queued task and lock it for processing.
    
    Implements optimistic locking to prevent concurrent processing by multiple workers.
    Locks expired locks (older than WORKER_LOCK_TIMEOUT_SECONDS) are considered available.
    
    Returns:
        Task if available and successfully locked, None otherwise
    """
    current_time = utcnow()
    lock_timeout = get_worker_lock_timeout_seconds()
    lock_threshold = current_time - timedelta(seconds=lock_timeout)
    
    # Find unlocked or expired-locked tasks
    statement = (
        select(Task)
        .where(
            Task.status == "queued",
            Task.is_test == is_test_mode(),
            or_(
                # Not locked at all
                and_(Task.locked_at == None, Task.locked_by == None),
                # Lock expired
                Task.locked_at < lock_threshold,
            ),
            (Task.scheduled_after == None) | (Task.scheduled_after <= current_time),
        )
        .order_by(Task.execution_order, Task.id)
        .limit(1)
        .with_for_update()  # Pessimistic lock to prevent race conditions
    )
    
    task = session.exec(statement).first()
    
    if task:
        # Lock the task atomically
        task.locked_at = current_time
        task.locked_by = WORKER_INSTANCE_ID
        task.updated_at = current_time
        session.add(task)
        session.commit()
        session.refresh(task)
        
        logger.info(
            "Locked task %d for processing (worker: %s, status: %s)",
            task.id, WORKER_INSTANCE_ID, task.status
        )
    
    return task


def _mark_task_in_progress(task: Task, session: Session) -> Task:
    task.status = "in_progress"
    task.updated_at = utcnow()
    # Keep lock info for audit trail
    _commit_and_refresh(session, task)
    logger.info(
        "Task %d now in_progress (locked by: %s)",
        task.id, task.locked_by
    )
    return task


def _mark_task_done(task: Task, result_text: str, session: Session) -> Task:
    task.status = "done"
    task.last_result = result_text
    task.updated_at = utcnow()
    # Clear lock on completion
    task.locked_at = None
    task.locked_by = None
    _commit_and_refresh(session, task)
    logger.info(
        "Task %d completed, lock released (was locked by: %s)",
        task.id, task.locked_by
    )
    return task


def _create_dlq_entry(task: Task, session: Session) -> DeadLetterQueue:
    """Create a Dead Letter Queue entry for a failed task."""
    dlq_entry = DeadLetterQueue(
        task_id=task.id,
        source_type=task.source_type,
        source_id=task.source_id,
        task_title=task.title,
        task_prompt=task.prompt,
        verification_prompt=task.verification_prompt,
        final_status="max_retries_exceeded",
        failure_reason="Max retries exceeded",
        failure_details=task.last_result or "No execution output",
        last_execution_output=task.last_result,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        failed_at=utcnow(),
        created_at=utcnow(),
    )
    session.add(dlq_entry)
    session.commit()
    session.refresh(dlq_entry)
    logger.info(
        "Created DLQ entry id=%d for task_id=%d after %d retries",
        dlq_entry.id, task.id, task.retry_count
    )
    return dlq_entry


def _requeue_or_fail_task(task: Task, result_text: str, session: Session) -> Task:
    task.retry_count += 1
    task.last_result = result_text
    task.updated_at = utcnow()

    if task.retry_count >= task.max_retries:
        task.status = "failed"
        task.scheduled_after = None
        # Clear lock on failure
        task.locked_at = None
        task.locked_by = None
        _create_dlq_entry(task, session)
    else:
        task.status = "queued"
        backoff_delay = _calculate_backoff_delay(task.retry_count)
        task.scheduled_after = datetime.fromtimestamp(
            utcnow().timestamp() + backoff_delay, timezone.utc
        )
        # Clear lock for requeue
        task.locked_at = None
        task.locked_by = None
        logger.info(
            "Task %d retry %d/%d, backoff delay: %.2f seconds, available after: %s",
            task.id,
            task.retry_count,
            task.max_retries,
            backoff_delay,
            task.scheduled_after.isoformat()
        )

    _commit_and_refresh(session, task)
    return task


def _mark_source_done(task: Task, session: Session) -> None:
    if task.source_type == "work_package":
        work_package = session.get(WorkPackage, task.source_id)
        if work_package:
            work_package.status = "done"
            work_package.updated_at = utcnow()
            session.add(work_package)
            session.commit()

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

    start_time = time.time()
    task = _mark_task_in_progress(task, session)

    try:
        # Check if task uses OpenCode ACP
        if task.opencode_project_path:
            # Use ACP-based execution
            session_service = _get_session_service()
            
            # Create session if not exists
            if not task.opencode_session_id:
                task = session_service.create_session(session, task)
            
            # Monitor session
            session_service.monitor_sessions(session)
            
            # Refresh task
            session.refresh(task)
            
            # Check if session is complete
            if task.opencode_status.value == "completed":
                task = session_service.complete_session(session, task)
                _mark_source_done(task, session)
                metrics.increment_task_processed("done")
                return task
            elif task.opencode_status.value == "failed":
                metrics.increment_task_processed("failed")
                return task
            else:
                # Session still running, return for later processing
                metrics.increment_task_processed("running")
                return task
        else:
            # Legacy REST-based execution
            execution_result = execute_with_opencode(
                prompt=task.prompt,
                verification_prompt=task.verification_prompt,
            )
            
            duration = time.time() - start_time
            metrics.observe_task_duration(duration)

            validation = validate_task_result(execution_result.raw_output)

            if validation.is_done:
                task = _mark_task_done(task, execution_result.raw_output, session)
                _mark_source_done(task, session)
                metrics.increment_task_processed("done")
                return task

            metrics.increment_task_processed("retry")
            metrics.increment_task_retry(task.source_type)
            return _requeue_or_fail_task(task, execution_result.raw_output, session)
            
    except Exception as e:
        duration = time.time() - start_time
        metrics.observe_task_duration(duration)
        metrics.increment_task_processed("failed")
        
        error_type = "execution_error"
        if "timeout" in str(e).lower():
            error_type = "timeout"
        elif "connection" in str(e).lower():
            error_type = "connection_error"
        
        metrics.increment_error(error_type)
        logger.error(f"Task {task_id} failed with {error_type}: {e}")
        
        # Requeue or fail based on retry count
        task.last_result = str(e)
        task.updated_at = utcnow()
        task.locked_at = None
        task.locked_by = None
        
        if task.retry_count >= task.max_retries - 1:
            task.status = "failed"
            _create_dlq_entry(task, session)
        else:
            task.status = "queued"
            task.retry_count += 1
            
        _commit_and_refresh(session, task)
        return task


def run_next_task(session: Session) -> Optional[Task]:
    task = get_next_queued_task(session)
    if not task:
        return None
    return run_task(task.id, session)
