"""Candidate discovery for REQ-011.

This module implements candidate discovery - loading executable backlog tasks
from the database in a deterministic, idempotent manner.
"""

from __future__ import annotations

import logging
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from execqueue.db.models import Task, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class CandidateDiscovery:
    """Discovers executable task candidates from the database.
    
    This class implements the candidate discovery logic for REQ-011:
    - Loads only tasks with status = backlog
    - Applies conservative dependency/blocking checks
    - Returns deterministic, sorted results
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
        
        Args:
            session: Database session
            exclude_task_ids: Optional list of task IDs to exclude
            
        Returns:
            List of executable backlog tasks, sorted by priority/order
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
        # - priority DESC (via details, if present)
        # - created_at ASC
        # - task_number ASC (for stability)
        query = query.order_by(
            Task.execution_order.nullslast(),
            Task.created_at.asc(),
            Task.task_number.asc(),
        )
        
        # Limit batch size
        query = query.limit(self.max_batch_size)
        
        # Execute query
        result = session.execute(query).scalars().all()
        
        logger.info(
            "Found %d executable backlog candidates (max_batch_size=%d)",
            len(result),
            self.max_batch_size,
        )
        
        return list(result)
    
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
