"""Recovery handling for stale queued tasks (REQ-011 AP 07).

This module handles:
1. Preparation failure classification
2. Stale queued task recovery
3. Retry exhaustion handling
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from execqueue.db.models import Task, TaskStatus
from execqueue.orchestrator.models import PreparationErrorType

logger = logging.getLogger(__name__)


class PreparationErrorClassifier:
    """Classifies preparation errors for recovery decisions."""
    
    # Error patterns for classification
    RECOVERABLE_PATTERNS = [
        "timeout",
        "temporary",
        "connection",
        "network",
        "lock",
        "resource temporarily unavailable",
    ]
    
    CONFLICT_PATTERNS = [
        "branch already exists",
        "worktree already exists",
        "dirty",
        "conflict",
        "blocked",
    ]
    
    NON_RECOVERABLE_PATTERNS = [
        "invalid",
        "not found",
        "permission denied",
        "security",
        "validation failed",
        "malformed",
    ]
    
    @classmethod
    def classify_error(cls, error_message: str) -> PreparationErrorType:
        """Classify an error message.
        
        Args:
            error_message: Error message to classify
            
        Returns:
            Error type classification
        """
        message_lower = error_message.lower()
        
        # Check non-recoverable first (highest priority)
        for pattern in cls.NON_RECOVERABLE_PATTERNS:
            if pattern in message_lower:
                return PreparationErrorType.NON_RECOVERABLE
        
        # Check conflict patterns
        for pattern in cls.CONFLICT_PATTERNS:
            if pattern in message_lower:
                return PreparationErrorType.CONFLICT
        
        # Check recoverable patterns
        for pattern in cls.RECOVERABLE_PATTERNS:
            if pattern in message_lower:
                return PreparationErrorType.RECOVERABLE
        
        # Default to recoverable for unknown errors
        return PreparationErrorType.RECOVERABLE


class StaleQueuedRecovery:
    """Handles recovery of stale queued tasks.
    
    A task is considered stale if it has been in 'queued' status longer
    than the configured timeout without progress.
    """
    
    def __init__(
        self,
        stale_timeout_minutes: int = 30,
        max_preparation_attempts: int = 3,
    ):
        """Initialize recovery handler.
        
        Args:
            stale_timeout_minutes: Minutes before a queued task is considered stale
            max_preparation_attempts: Maximum preparation attempts before failure
        """
        self.stale_timeout = timedelta(minutes=stale_timeout_minutes)
        self.max_attempts = max_preparation_attempts
    
    def find_stale_tasks(
        self,
        session: Session,
        worker_id: str | None = None,
    ) -> list[Task]:
        """Find tasks that are stale in queued status.
        
        Args:
            session: Database session
            worker_id: Optional worker ID to filter by
            
        Returns:
            List of stale queued tasks
        """
        stale_threshold = datetime.utcnow() - self.stale_timeout
        
        query = (
            select(Task)
            .where(Task.status == TaskStatus.QUEUED.value)
            .where(Task.queued_at <= stale_threshold)
        )
        
        if worker_id:
            query = query.where(Task.locked_by == worker_id)
        
        result = session.execute(query).scalars().all()
        
        logger.info("Found %d stale queued tasks", len(result))
        
        return list(result)
    
    def recover_task(
        self,
        session: Session,
        task: Task,
        last_error: str | None = None,
    ) -> tuple[TaskStatus, str]:
        """Recover a stale task.
        
        Args:
            session: Database session
            task: Stale task to recover
            last_error: Last error message (optional)
            
        Returns:
            Tuple of (new_status, recovery_reason)
        """
        # Determine error type
        if last_error:
            error_type = PreparationErrorClassifier.classify_error(last_error)
        else:
            error_type = PreparationErrorType.RECOVERABLE
        
        # Check retry exhaustion
        if (task.preparation_attempt_count or 0) >= self.max_attempts:
            logger.warning(
                "Task %s: retry exhausted (attempts=%d)",
                task.task_number,
                task.preparation_attempt_count,
            )
            return TaskStatus.FAILED, "Retry exhaustion"
        
        # Check for non-recoverable errors
        if error_type == PreparationErrorType.NON_RECOVERABLE:
            logger.warning(
                "Task %s: non-recoverable error",
                task.task_number,
            )
            return TaskStatus.FAILED, "Non-recoverable error"
        
        # Check for conflict - could retry or fail depending on policy
        if error_type == PreparationErrorType.CONFLICT:
            # For conflicts, we return to backlog with a note
            logger.info(
                "Task %s: conflict detected, returning to backlog",
                task.task_number,
            )
            return TaskStatus.BACKLOG, "Conflict - retry allowed"
        
        # Default: recoverable error, return to backlog
        logger.info(
            "Task %s: recoverable error, returning to backlog",
            task.task_number,
        )
        return TaskStatus.BACKLOG, "Recoverable error"
    
    def run_recovery_cycle(
        self,
        session: Session,
        worker_id: str | None = None,
    ) -> list[tuple[Task, TaskStatus, str]]:
        """Run a full recovery cycle.
        
        Args:
            session: Database session
            worker_id: Optional worker ID to filter by
            
        Returns:
            List of (task, new_status, reason) tuples
        """
        logger.info("Starting stale queued recovery cycle")
        
        stale_tasks = self.find_stale_tasks(session, worker_id)
        results: list[tuple[Task, TaskStatus, str]] = []
        
        for task in stale_tasks:
            # Get last error
            last_error = task.last_preparation_error
            
            # Determine recovery action
            new_status, reason = self.recover_task(session, task, last_error)
            
            # Update task
            task.status = new_status.value
            task.queued_at = None
            task.locked_by = None
            
            # If returning to backlog, reset some fields
            if new_status == TaskStatus.BACKLOG:
                task.preparation_attempt_count = 0
                task.last_preparation_error = None
            
            task.updated_at = datetime.utcnow()
            
            results.append((task, new_status, reason))
            
            logger.info(
                "Recovered task %s: %s -> %s (%s)",
                task.task_number,
                TaskStatus.QUEUED.value,
                new_status.value,
                reason,
            )
        
        session.commit()
        
        logger.info(
            "Recovery cycle complete: %d tasks processed",
            len(results),
        )
        
        return results


# Recovery Matrix documentation
RECOVERY_MATRIX = """
Recovery Matrix for Preparation Errors:

| Zustand                              | Beispiel                                    | Zielstatus | Bedingung                    |
|--------------------------------------|---------------------------------------------|------------|------------------------------|
| Recoverable ohne Side Effects        | temporärer DB-/Config-/Git-Read-Fehler     | backlog    | attempt < max                |
| Recoverable mit task-owned Side Eff. | Worktree teilweise erzeugt, task-owned      | backlog/failed | nur nach safe cleanup    |
| Conflict                             | Branch/Worktree von anderem Task belegt     | backlog    | abhängig von Retry-Policy    |
| Non-recoverable                      | invalider Pfad, Security Guard verletzt     | failed     | sofort                       |
| Retry exhausted                      | wiederholte recoverable Fehler              | failed     | attempt >= max               |
| in_progress                          | Runner läuft oder lief an                   | keine      | außerhalb REQ-011            |
"""
