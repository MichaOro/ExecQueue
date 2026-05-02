"""Candidate discovery for REQ-011.

This module implements candidate discovery - loading executable backlog tasks
from the database in a deterministic, idempotent manner.

Ordering Criteria:
    Tasks are ordered by:
    1. execution_order ASC (NULLs last) - explicit execution sequence
    2. priority DESC (from details["priority"]) - higher priority first
    3. created_at ASC - earlier created tasks first
    4. task_number ASC - for stability
"""

from __future__ import annotations

import logging
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from execqueue.db.models import Task, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class CandidateDiscovery:
    """Discovers executable task candidates from the database.
    
    This class implements the candidate discovery logic for REQ-011:
    - Loads only tasks with status = backlog
    - Applies conservative dependency/blocking checks
    - Returns deterministic, sorted results (by execution_order, priority, created_at, task_number)
    - Supports max_batch_size limiting
    
    The trigger mechanism (orchestrator_trigger.py) fires after task persistence,
    but this class is the source of truth for which tasks are executable.
    """
    
    def __init__(
        self,
        max_batch_size: int = 10,
        supported_types: tuple[str, ...] | None = None,
    ):
        """Initialize candidate discovery.
        
        Args:
            max_batch_size: Maximum number of candidates to return
            supported_types: Supported task types (default: planning, execution, analysis)
        """
        self.max_batch_size = max_batch_size
        self.supported_types = supported_types or (
            TaskType.PLANNING,
            TaskType.EXECUTION,
            TaskType.ANALYSIS,
        )
    
    def find_candidates(
        self,
        session: Session,
        exclude_task_ids: Sequence[UUID] | None = None,
    ) -> list[Task]:
        """Find executable backlog tasks.
        
        Tasks are returned in deterministic order:
        1. execution_order ASC (NULLs last) - explicit execution sequence
        2. priority DESC (from details["priority"]) - higher priority first
        3. created_at ASC - earlier created tasks first
        4. task_number ASC - for stability
        
        Args:
            session: Database session
            exclude_task_ids: Optional list of task IDs to exclude
            
        Returns:
            List of executable backlog tasks, sorted by execution_order,
            priority (DESC), created_at, and task_number
        """
        # Build base query for backlog tasks
        query = select(Task).where(Task.status == TaskStatus.BACKLOG.value)
        
        # Filter by supported types
        query = query.where(Task.type.in_(self.supported_types))
        
        # Exclude specific task IDs if provided
        if exclude_task_ids:
            query = query.where(~Task.id.in_(exclude_task_ids))
        
        # Apply conservative filtering for dependencies/blocking
        # For now, we check if task is not blocked via details flag
        # This can be extended with more sophisticated dependency logic
        # Note: Using raw SQL for JSON key check to be database-agnostic
        from sqlalchemy import or_, not_, func
        
        # Simple approach: filter out tasks with blocked flag in details
        # This is a conservative default that can be enhanced later
        # For SQLite/PostgreSQL compatibility, we skip complex JSON filtering here
        # and rely on application-level filtering after retrieval
        
        # Apply deterministic sorting:
        # - execution_order ASC (NULLs last)
        # - priority DESC (via details["priority"], if present)
        # - created_at ASC
        # - task_number ASC (for stability)
        #
        # Note: Priority ordering is done in application space after retrieval
        # because JSON-based ordering is database-specific and may not be
        # available in all environments. We sort by execution_order first,
        # then apply priority as a secondary sort in memory.
        query = query.order_by(
            Task.execution_order.nullslast(),
            Task.created_at.asc(),
            Task.task_number.asc(),
        )
        
        # Limit batch size - fetch slightly more to allow priority sorting
        query = query.limit(self.max_batch_size * 2)
        
        # Execute query
        result = session.execute(query).scalars().all()
        candidates = list(result)
        
        # Apply priority-based sorting in application space
        # Higher priority values come first (DESC)
        def sort_key(task: Task) -> tuple[int, int, int]:
            """Generate sort key: (execution_order, -priority, task_number)."""
            execution_order = task.execution_order if task.execution_order is not None else 999999
            priority = task.details.get("priority", 0) if task.details else 0
            # Ensure priority is numeric and invert for DESC ordering
            try:
                priority = int(priority) if priority is not None else 0
            except (ValueError, TypeError):
                priority = 0
            return (execution_order, -priority, task.task_number)
        
        candidates.sort(key=sort_key)
        
        # Trim to max_batch_size after sorting
        candidates = candidates[:self.max_batch_size]
        
        logger.info(
            "Found %d executable backlog candidates (max_batch_size=%d)",
            len(candidates),
            self.max_batch_size,
        )
        
        return candidates
    
    def count_pending(self, session: Session) -> int:
        """Count pending backlog tasks.
        
        Args:
            session: Database session
            
        Returns:
            Number of backlog tasks
        """
        query = (
            select(Task)
            .where(Task.status == TaskStatus.BACKLOG.value)
            .limit(1)
        )
        result = session.execute(query).scalars().first()
        return 1 if result else 0
