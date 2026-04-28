"""Atomic locking and queued transition for REQ-011.

This module implements atomic task claiming with the backlog->queued transition.
It ensures no two workers can claim the same task.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from execqueue.db.models import Task, TaskStatus
from execqueue.orchestrator.models import BatchPlan, BatchType

logger = logging.getLogger(__name__)


@dataclass
class LockResult:
    """Result of a locking operation."""
    
    success: bool
    locked_task_ids: list[UUID]
    failed_task_ids: list[UUID]
    failure_reasons: dict[UUID, str]
    affected_rows: int
    expected_rows: int


class TaskLocker:
    """Handles atomic task locking with backlog->queued transition.
    
    Concurrency invariant:
    - Two workers must never claim the same task
    - Only tasks with status=backlog can be locked
    - Affected row count must match expected count
    
    The lock is short-lived and does not include Git/Filesystem operations.
    """
    
    def __init__(self, worker_id: str):
        """Initialize task locker.
        
        Args:
            worker_id: Unique identifier for this worker
        """
        self.worker_id = worker_id
    
    def lock_tasks(
        self,
        session: Session,
        batch_plan: BatchPlan,
    ) -> LockResult:
        """Atomically lock tasks from a batch plan.
        
        Args:
            session: Database session
            batch_plan: Batch plan with task IDs to lock
            
        Returns:
            LockResult with success/failure information
        """
        if not batch_plan.task_ids:
            return LockResult(
                success=True,
                locked_task_ids=[],
                failed_task_ids=[],
                failure_reasons={},
                affected_rows=0,
                expected_rows=0,
            )
        
        expected_rows = len(batch_plan.task_ids)
        now = datetime.utcnow()
        
        try:
            # Build atomic update query
            # Only update tasks that are still in backlog status
            update_stmt = (
                update(Task)
                .where(Task.id.in_(batch_plan.task_ids))
                .where(Task.status == TaskStatus.BACKLOG.value)
                .values(
                    status=TaskStatus.QUEUED.value,
                    queued_at=now,
                    locked_by=self.worker_id,
                    batch_id=batch_plan.batch_id,
                    updated_at=now,
                )
                .execution_options(synchronize_session="fetch")
            )
            
            # Execute update
            result = session.execute(update_stmt)
            affected_rows = result.rowcount
            
            # Validate affected rows match expected
            if affected_rows != expected_rows:
                # Some tasks were already claimed by another worker
                session.rollback()
                
                # Identify which tasks failed
                failed_ids: list[UUID] = []
                success_ids: list[UUID] = []
                
                for task_id in batch_plan.task_ids:
                    # Check current status of each task
                    task = session.get(Task, task_id)
                    if task and task.status != TaskStatus.BACKLOG.value:
                        failed_ids.append(task_id)
                    else:
                        success_ids.append(task_id)
                
                logger.warning(
                    "Lock conflict detected: expected %d rows, got %d. "
                    "Failed tasks: %s",
                    expected_rows,
                    affected_rows,
                    failed_ids,
                )
                
                return LockResult(
                    success=False,
                    locked_task_ids=success_ids,
                    failed_task_ids=failed_ids,
                    failure_reasons={tid: "Already claimed by another worker" for tid in failed_ids},
                    affected_rows=affected_rows,
                    expected_rows=expected_rows,
                )
            
            # Commit the transaction
            session.commit()
            
            logger.info(
                "Successfully locked %d tasks in batch %s (worker=%s)",
                affected_rows,
                batch_plan.batch_id,
                self.worker_id,
            )
            
            return LockResult(
                success=True,
                locked_task_ids=list(batch_plan.task_ids),
                failed_task_ids=[],
                failure_reasons={},
                affected_rows=affected_rows,
                expected_rows=expected_rows,
            )
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error("Database error during locking: %s", e)
            
            return LockResult(
                success=False,
                locked_task_ids=[],
                failed_task_ids=list(batch_plan.task_ids),
                failure_reasons={tid: f"Database error: {e}" for tid in batch_plan.task_ids},
                affected_rows=0,
                expected_rows=expected_rows,
            )
    
    def lock_single_task(
        self,
        session: Session,
        task_id: UUID,
        batch_id: str | None = None,
    ) -> LockResult:
        """Atomically lock a single task.
        
        Args:
            session: Database session
            task_id: Task UUID to lock
            batch_id: Optional batch ID for correlation
            
        Returns:
            LockResult with success/failure information
        """
        now = datetime.utcnow()
        
        try:
            update_stmt = (
                update(Task)
                .where(Task.id == task_id)
                .where(Task.status == TaskStatus.BACKLOG.value)
                .values(
                    status=TaskStatus.QUEUED.value,
                    queued_at=now,
                    locked_by=self.worker_id,
                    batch_id=batch_id,
                    updated_at=now,
                )
            )
            
            result = session.execute(update_stmt)
            affected_rows = result.rowcount
            
            if affected_rows != 1:
                session.rollback()
                task = session.get(Task, task_id)
                current_status = task.status if task else "not_found"
                
                logger.warning(
                    "Failed to lock task %s: status was %s (expected backlog)",
                    task_id,
                    current_status,
                )
                
                return LockResult(
                    success=False,
                    locked_task_ids=[],
                    failed_task_ids=[task_id],
                    failure_reasons={task_id: f"Task status was {current_status}"},
                    affected_rows=affected_rows,
                    expected_rows=1,
                )
            
            session.commit()
            
            logger.info(
                "Successfully locked task %s (worker=%s, batch=%s)",
                task_id,
                self.worker_id,
                batch_id,
            )
            
            return LockResult(
                success=True,
                locked_task_ids=[task_id],
                failed_task_ids=[],
                failure_reasons={},
                affected_rows=1,
                expected_rows=1,
            )
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error("Database error locking task %s: %s", task_id, e)
            
            return LockResult(
                success=False,
                locked_task_ids=[],
                failed_task_ids=[task_id],
                failure_reasons={task_id: f"Database error: {e}"},
                affected_rows=0,
                expected_rows=1,
            )
    
    def release_lock(
        self,
        session: Session,
        task_id: UUID,
        target_status: TaskStatus = TaskStatus.BACKLOG,
    ) -> bool:
        """Release a lock by setting task to target status.
        
        Args:
            session: Database session
            task_id: Task UUID to release
            target_status: Status to set (default: backlog)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_stmt = (
                update(Task)
                .where(Task.id == task_id)
                .where(Task.status == TaskStatus.QUEUED.value)
                .values(
                    status=target_status.value,
                    queued_at=None,
                    locked_by=None,
                    updated_at=datetime.utcnow(),
                )
            )
            
            result = session.execute(update_stmt)
            session.commit()
            
            if result.rowcount == 1:
                logger.info("Released lock for task %s -> %s", task_id, target_status.value)
                return True
            else:
                logger.warning("Failed to release lock for task %s (not in queued state)", task_id)
                return False
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error("Error releasing lock for task %s: %s", task_id, e)
            return False
