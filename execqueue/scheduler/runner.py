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
from execqueue.validation.task_validator import validate_task_result, ValidationErrorType
from execqueue.validation.policy_loader import (
    get_retry_policy,
    calculate_backoff_seconds,
    should_retry,
    should_escalate,
)
from execqueue.workers.opencode_adapter import execute_with_opencode, OpenCodeACPClient
from execqueue.services.opencode_session_service import OpenCodeSessionService
from execqueue.services.status_sync_service import sync_task_status_to_parent
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


def check_queue_blocked(session: Session, is_test: bool) -> bool:
    """
    Prüft ob die Queue durch einen block_queue Task blockiert ist.
    
    Args:
        session: Datenbank-Session
        is_test: Test-Modus Flag
        
    Returns:
        True wenn Queue blockiert ist
    """
    blocking_task = session.exec(
        select(Task)
        .where(
            Task.block_queue == True,
            Task.status.in_(["queued", "in_progress"]),
            Task.is_test == is_test,
        )
        .limit(1)
    ).first()
    
    return blocking_task is not None


def get_parallel_task_count(session: Session, is_test: bool) -> int:
    """
    Zählt die Anzahl aktuell paralleler Tasks.
    
    Args:
        session: Datenbank-Session
        is_test: Test-Modus Flag
        
    Returns:
        Anzahl paralleler Tasks
    """
    count = session.exec(
        select(Task)
        .where(
            Task.parallelization_allowed == True,
            Task.status.in_(["queued", "in_progress"]),
            Task.is_test == is_test,
        )
    ).count()
    
    return count


def _check_task_dependencies(task: Task, session: Session) -> bool:
    """
    Prüft ob alle Dependencies eines Tasks erfüllt sind.
    
    Args:
        task: Der zu prüfende Task
        session: Datenbank-Session
        
    Returns:
        True wenn alle Dependencies erfüllt sind oder keine existieren, False sonst
    """
    if task.source_type != "work_package":
        # Nur WorkPackages haben Dependencies
        return True
    
    work_package = session.get(WorkPackage, task.source_id)
    if not work_package or not work_package.dependency_id:
        # Kein WorkPackage oder keine Dependency - kann verarbeitet werden
        return True
    
    # Dependency-WorkPackage laden und prüfen
    dependency = session.get(WorkPackage, work_package.dependency_id)
    if not dependency:
        logger.warning(
            "Dependency not found for work_package %d (dependency_id: %d)",
            work_package.id, work_package.dependency_id
        )
        return False
    
    if dependency.queue_status != "done":
        logger.debug(
            "Task %d blocked by dependency: WorkPackage %d is in status '%s' (not 'done')",
            task.id, dependency.id, dependency.queue_status
        )
        return False
    
    logger.debug(
        "Task %d dependency satisfied: WorkPackage %d is 'done'",
        task.id, dependency.id
    )
    return True


def get_next_queued_task(session: Session) -> Optional[Task]:
    """
    Get next queued task and lock it for processing.
    
    Implements optimistic locking to prevent concurrent processing by multiple workers.
    Locks expired locks (older than WORKER_LOCK_TIMEOUT_SECONDS) are considered available.
    
    Queue-Steuerung:
    - block_queue: Wenn True, keine weiteren Tasks verarbeiten
    - schedulable: Nur Tasks mit schedulable=True vom Scheduler verarbeiten
    - parallelization_allowed: Berücksichtigung bei paralleler Ausführung
    - dependency_id: WorkPackages mit Dependencies warten auf Erfüllung
    
    Returns:
        Task if available and successfully locked, None otherwise
    """
    current_time = utcnow()
    lock_timeout = get_worker_lock_timeout_seconds()
    lock_threshold = current_time - timedelta(seconds=lock_timeout)
    is_test = is_test_mode()
    
    # Prüfen ob Queue blockiert ist
    if check_queue_blocked(session, is_test):
        logger.debug("Queue is blocked by a block_queue task, skipping")
        return None
    
    # Find unlocked or expired-locked tasks
    # Filter nach: schedulable=True, nicht blockierend, scheduled_after erfüllt
    statement = (
        select(Task)
        .where(
            Task.status == "queued",
            Task.is_test == is_test,
            Task.schedulable == True,  # Nur schedulable Tasks
            Task.block_queue == False,  # Keine blockierenden Tasks
            or_(
                # Not locked at all
                and_(Task.locked_at == None, Task.locked_by == None),
                # Lock expired
                Task.locked_at < lock_threshold,
            ),
            (Task.scheduled_after == None) | (Task.scheduled_after <= current_time),
        )
        .order_by(Task.execution_order, Task.id)
        .limit(10)  # Mehrere Tasks holen und Dependencies prüfen
        .with_for_update()  # Pessimistic lock to prevent race conditions
    )
    
    candidate_tasks = session.exec(statement).all()
    
    # Durchlaufe Kandidaten und prüfe Dependencies
    for task in candidate_tasks:
        if not _check_task_dependencies(task, session):
            continue  # Dependency nicht erfüllt, nächster Kandidat
        
        # Dependency erfüllt - Task locken
        task.locked_at = current_time
        task.locked_by = WORKER_INSTANCE_ID
        task.updated_at = current_time
        task.queue_status = "in_progress"  # Queue-Status aktualisieren
        session.add(task)
        session.commit()
        session.refresh(task)
        
        logger.info(
            "Locked task %d for processing (worker: %s, status: %s, queue_status: %s)",
            task.id, WORKER_INSTANCE_ID, task.status, task.queue_status
        )
        
        return task
    
    # Keine passenden Tasks gefunden
    return None


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
    task.queue_status = "done"  # Queue-Status aktualisieren
    # Clear lock on completion
    task.locked_at = None
    task.locked_by = None
    session.add(task)
    
    # Parent-Status synchronisieren (ohne Commit - wir machen es danach)
    sync_task_status_to_parent(task, session)
    
    # Atomic commit aller Änderungen
    session.commit()
    session.refresh(task)
    
    logger.info(
        "Task %d completed, lock released (was locked by: %s, queue_status: %s)",
        task.id, task.locked_by, task.queue_status
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
    """
    Markiert die Source-Entität (WorkPackage oder Requirement) als done.
    
    HINWEIS: Diese Funktion führt KEIN commit aus. Der Caller kontrolliert
    die Transaction-Granularität.
    
    Args:
        task: Der abgeschlossene Task
        session: Datenbank-Session
    """
    if task.source_type == "work_package":
        work_package = session.get(WorkPackage, task.source_id)
        if work_package:
            work_package.status = "done"
            work_package.updated_at = utcnow()
            session.add(work_package)

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

    elif task.source_type == "requirement":
        requirement = session.get(Requirement, task.source_id)
        if requirement:
            requirement.status = "done"
            requirement.updated_at = utcnow()
            session.add(requirement)
    # KEIN commit hier - Caller macht das


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
            
            # Monitor session and check for timeouts
            updated_tasks = session_service.monitor_sessions(session)
            
            # Check if any sessions need wake-up (waiting too long)
            for updated_task in updated_tasks:
                if updated_task.opencode_status == OpenCodeSessionStatus.WAITING:
                    time_waiting = (datetime.now(timezone.utc) - (updated_task.opencode_last_ping or datetime.now(timezone.utc))).total_seconds()
                    timeout_threshold = get_opencode_session_timeout() / 2
                    
                    if time_waiting > timeout_threshold:
                        logger.info(
                            "Auto wake-up for task %d: waiting %ds > threshold %ds",
                            updated_task.id,
                            time_waiting,
                            timeout_threshold
                        )
                        session_service.wake_up_session(session, updated_task, prompt="Fahre fort")
            
            # Cleanup expired sessions
            expired_count = session_service.cleanup_expired_sessions(
                session,
                timeout_seconds=get_opencode_session_timeout()
            )
            if expired_count > 0:
                logger.info("Cleaned up %d expired sessions", expired_count)
            
            # Refresh current task
            session.refresh(task)
            
            # Check if session is complete
            if task.opencode_status.value == "completed":
                task = session_service.complete_session(session, task)
                # Atomic commit for source done
                _mark_source_done(task, session)
                session.commit()
                metrics.increment_task_processed("done")
                return task
            elif task.opencode_status.value == "failed":
                session.commit()
                metrics.increment_task_processed("failed")
                return task
            else:
                # Session still running, return for later processing
                session.commit()
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

            validation = validate_task_result(
                execution_result.raw_output,
                retry_count=task.retry_count
            )
            
            # Validation Metrics erfassen
            validation_duration = time.time() - start_time  # Näherung
            if validation.is_done:
                metrics.increment_validation_result("success", "none")
            else:
                metrics.increment_validation_result("failure", validation.error_type)
                metrics.increment_validation_retry(validation.error_type)
            metrics.observe_validation_duration(validation_duration)

            # Logging des Validierungsergebnisses
            logger.info(
                "Task %d validation result: is_done=%s, error_type=%s, passes=%s",
                task.id,
                validation.is_done,
                validation.error_type,
                validation.validation_passes
            )
            
            if validation.is_done:
                # Atomic update: Task done + Source done + Status sync
                task.status = "done"
                task.last_result = execution_result.raw_output
                task.updated_at = utcnow()
                task.queue_status = "done"
                task.locked_at = None
                task.locked_by = None
                session.add(task)
                
                # Synchronize to parent entities
                sync_task_status_to_parent(task, session)
                _mark_source_done(task, session)
                
                # Atomic commit
                session.commit()
                session.refresh(task)
                
                metrics.increment_task_processed("done")
                return task

            # Validierung fehlgeschlagen - differenzierte Retry-Logik
            metrics.increment_task_processed("retry")
            metrics.increment_task_retry(task.source_type)
            
            # Kritische Fehler - direkter Fail ohne Retry
            if validation.error_type == ValidationErrorType.CRITICAL:
                logger.error(
                    "Task %d critical validation failure: %s",
                    task.id,
                    validation.error_details
                )
                task.status = "failed"
                task.last_result = f"Critical validation error: {'; '.join(validation.error_details)}"
                _create_dlq_entry(task, session)
                _commit_and_refresh(session, task)
                return task
            
            # Retry-Logik mit differenziertem Backoff
            task.last_result = execution_result.raw_output
            task.updated_at = utcnow()
            
            # Berechne Backoff basierend auf Fehlertyp
            backoff_delay = validation.backoff_seconds
            task.retry_count += 1
            
            if task.retry_count >= task.max_retries:
                # Max Retries erreicht - DLQ
                logger.warning(
                    "Task %d max retries exceeded after %d retries (error_type: %s)",
                    task.id,
                    task.retry_count,
                    validation.error_type
                )
                task.status = "failed"
                task.scheduled_after = None
                task.locked_at = None
                task.locked_by = None
                _create_dlq_entry(task, session)
            else:
                # Requeue mit Backoff
                task.status = "queued"
                task.scheduled_after = datetime.fromtimestamp(
                    utcnow().timestamp() + backoff_delay, timezone.utc
                )
                task.locked_at = None
                task.locked_by = None
                
                logger.info(
                    "Task %d retry %d/%d (error_type: %s), backoff: %.2fs, available: %s",
                    task.id,
                    task.retry_count,
                    task.max_retries,
                    validation.error_type,
                    backoff_delay,
                    task.scheduled_after.isoformat()
                )
            
            _commit_and_refresh(session, task)
            return task
            
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
