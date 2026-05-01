"""Session strategy for hybrid execution (REQ-016)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID
    from execqueue.opencode.client import OpenCodeClient

logger = logging.getLogger(__name__)


@dataclass
class SessionAssignment:
    """Assignment of tasks to OpenCode sessions.

    Attributes:
        session_id: OpenCode session identifier (placeholder or actual)
        task_ids: List of task_ids assigned to this session
        is_sequential: True if this session is for a sequential path
    """

    session_id: str
    task_ids: list[UUID]
    is_sequential: bool


@dataclass
class SessionPlan:
    """Complete session plan for workflow execution.

    Attributes:
        assignments: List of session assignments
    """

    assignments: list[SessionAssignment] = field(default_factory=list)

    @property
    def sequential_count(self) -> int:
        """Number of sequential sessions."""
        return sum(1 for a in self.assignments if a.is_sequential)

    @property
    def parallel_count(self) -> int:
        """Number of parallel sessions."""
        return sum(1 for a in self.assignments if not a.is_sequential)

    def get_session_for_task(self, task_id: UUID) -> str | None:
        """Get session_id for a given task_id.

        Args:
            task_id: Task identifier

        Returns:
            Session ID or None if not found
        """
        for assignment in self.assignments:
            if task_id in assignment.task_ids:
                return assignment.session_id
        return None

    def get_tasks_for_session(self, session_id: str) -> list[UUID]:
        """Get task_ids for a given session_id.

        Args:
            session_id: Session identifier

        Returns:
            List of task IDs in this session
        """
        for assignment in self.assignments:
            if assignment.session_id == session_id:
                return assignment.task_ids
        return []


class HybridSessionStrategy:
    """Hybrid session strategy for REQ-016.

    Implements the hybrid strategy:
    - Sequential paths share one session
    - Parallel tasks get individual sessions

    Usage:
        strategy = HybridSessionStrategy(client)
        plan = strategy.create_plan(sequential_paths, all_task_ids)
        plan = await strategy.create_sessions(plan)
        for assignment in plan.assignments:
            for task_id in assignment.task_ids:
                session_id = plan.get_session_for_task(task_id)
                execute_task(task_id, session_id)
    """

    def __init__(self, opencode_client: OpenCodeClient):
        """Initialize strategy with OpenCode client.

        Args:
            opencode_client: OpenCode client for session creation
        """
        self._client = opencode_client

    def create_plan(
        self,
        sequential_paths: list[list[UUID]],
        all_task_ids: list[UUID],
    ) -> SessionPlan:
        """Create session plan from sequential paths and all tasks.

        Args:
            sequential_paths: List of sequential task chains from DependencyGraph
            all_task_ids: All task IDs in the workflow

        Returns:
            SessionPlan with placeholder session_ids

        Note:
            Tasks not in any sequential path are treated as parallel tasks
            and get individual sessions.
        """
        plan = SessionPlan()

        # Identify tasks in sequential paths
        sequential_task_ids = set()
        for path in sequential_paths:
            sequential_task_ids.update(path)

        # Assign sequential paths to shared sessions
        for path_idx, path in enumerate(sequential_paths):
            session_name = f"seq-{path_idx + 1}-{len(path)}tasks"
            plan.assignments.append(
                SessionAssignment(
                    session_id=session_name,  # Placeholder, actual ID from client
                    task_ids=path,
                    is_sequential=True,
                )
            )

        # Assign parallel tasks to individual sessions
        parallel_tasks = [
            task_id for task_id in all_task_ids
            if task_id not in sequential_task_ids
        ]

        for task_idx, task_id in enumerate(parallel_tasks):
            session_name = f"parallel-{task_idx + 1}-{task_id.hex[:8]}"
            plan.assignments.append(
                SessionAssignment(
                    session_id=session_name,  # Placeholder
                    task_ids=[task_id],
                    is_sequential=False,
                )
            )

        return plan

    async def create_sessions(self, plan: SessionPlan) -> SessionPlan:
        """Create actual OpenCode sessions for a plan.

        Args:
            plan: SessionPlan with placeholder session_ids

        Returns:
            SessionPlan with actual session_ids from OpenCode

        Note:
            This should be called once before workflow execution starts.
            Sessions remain open until cleanup_sessions() is called.
        """
        for assignment in plan.assignments:
            actual_session = await self._client.create_session(
                name=assignment.session_id
            )
            assignment.session_id = actual_session.id
            logger.info(
                f"Created session {actual_session.id} for "
                f"{'sequential' if assignment.is_sequential else 'parallel'} "
                f"tasks: {assignment.task_ids}"
            )

        return plan

    async def cleanup_sessions(self, plan: SessionPlan) -> None:
        """Close all sessions in a plan.

        Args:
            plan: SessionPlan with active sessions

        Note:
            Must be called after workflow execution to avoid resource leaks.
            Ignores errors to ensure all sessions are attempted to be closed.
        """
        # Collect unique session IDs (sequential paths share sessions)
        session_ids = set()
        for assignment in plan.assignments:
            session_ids.add(assignment.session_id)

        for session_id in session_ids:
            try:
                await self._client.close_session(session_id)
                logger.info(f"Closed session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to close session {session_id}: {e}")
