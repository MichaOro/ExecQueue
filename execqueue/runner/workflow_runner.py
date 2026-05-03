"""Workflow runner implementation for REQ-019.

Implements the WorkflowRunner that integrates with RunnerManager and
delegates to WorkflowExecutor for actual execution.

Key features:
- Standalone task optimization (len(tasks)==1 → direct execution)
- Multi-task workflow execution via DependencyGraph + Batches
- Proper lifecycle management and error handling
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from execqueue.orchestrator.workflow_models import WorkflowContext, WorkflowStatus
from execqueue.db.models import Task
from execqueue.runner.claim import ClaimFailedError, claim_task
from execqueue.runner.graph import DependencyGraph
from execqueue.runner.result_handler import ResultHandler
from execqueue.db.session import create_session

if TYPE_CHECKING:
    from uuid import UUID

    from execqueue.opencode.client import OpenCodeClient
    from execqueue.runner.git_workflow import GitWorkflowManager
    from execqueue.runner.session_strategy import HybridSessionStrategy
    from execqueue.runner.workflow_executor import TaskResult, WorkflowExecutor

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Concrete runner implementation for workflow execution (REQ-019).
    
    This runner implements the execution logic expected by RunnerManager.
    It delegates to WorkflowExecutor for multi-task workflows and performs
    direct execution for standalone tasks (single-task workflows).
    
    Execution modes:
    - Standalone (len(tasks)==1): Direct execution without graph overhead
    - Multi-task: Full workflow execution with dependency resolution
    
    Attributes:
        ctx: WorkflowContext to execute
        runner_uuid: Unique identifier for this runner instance
        opencode_client: OpenCode client for prompt dispatch (optional)
        session_strategy: Session strategy for hybrid execution (optional)
        git_manager: Git workflow manager for worktree operations (optional)
    """

    def __init__(
        self,
        ctx: WorkflowContext,
        runner_uuid: str,
        opencode_client: OpenCodeClient | None = None,
        session_strategy: HybridSessionStrategy | None = None,
        git_manager: GitWorkflowManager | None = None,
    ):
        """Initialize the workflow runner.
        
        Args:
            ctx: WorkflowContext containing tasks and dependencies
            runner_uuid: Unique identifier for this runner
            opencode_client: OpenCode client for prompt dispatch
            session_strategy: Session strategy for hybrid execution
            git_manager: Git workflow manager for worktree/commit operations
            
        Note:
            If opencode_client, session_strategy, or git_manager are None,
            the runner operates in mock mode (for testing).
        """
        self.ctx = ctx
        self.runner_uuid = runner_uuid
        self._opencode_client = opencode_client
        self._session_strategy = session_strategy
        self._git_manager = git_manager
        self._executor: WorkflowExecutor | None = None
        self._workflow_id = ctx.workflow_id
        self._results: list[TaskResult] = []

    async def run(self) -> list[TaskResult]:
        """Execute the workflow.
        
        This is the main entry point called by RunnerManager.
        
        Execution flow:
        1. Check for standalone task (len==1) → Direct execution
        2. Multi-task → Build graph, execute via WorkflowExecutor
        3. Handle errors and return results
        
        Returns:
            List of TaskResult for all executed tasks
            
        Raises:
            Exception: If workflow execution fails catastrophically
        """
        logger.info(
            "WorkflowRunner starting (runner=%s, workflow=%s, tasks=%d)",
            self.runner_uuid,
            self._workflow_id,
            len(self.ctx.tasks),
        )
        
        start_time = time.time()
        
        try:
            # Mark workflow as started
            self.ctx.started_at = time.time()
            
            # Standalone optimization: Single task → Direct execution
            if len(self.ctx.tasks) == 1:
                logger.info(
                    "WorkflowRunner: Standalone task detected (workflow=%s), "
                    "skipping graph overhead",
                    self._workflow_id,
                )
                self._results = await self._execute_standalone()
            else:
                # Multi-task: Full workflow execution
                logger.info(
                    "WorkflowRunner: Multi-task workflow (workflow=%s, tasks=%d), "
                    "using dependency graph",
                    self._workflow_id,
                    len(self.ctx.tasks),
                )
                self._results = await self._execute_with_graph()
            
            # Mark workflow as finished
            self.ctx.finished_at = time.time()
            duration = self.ctx.finished_at - (self.ctx.started_at or 0)
            
            logger.info(
                "WorkflowRunner completed (runner=%s, workflow=%s, "
                "tasks=%d, duration=%.2fs, results=%d)",
                self.runner_uuid,
                self._workflow_id,
                len(self.ctx.tasks),
                duration,
                len(self._results),
            )
            
            return self._results
            
        except Exception as e:
            # Mark workflow as failed
            self.ctx.finished_at = time.time()
            self.ctx.error_message = str(e)
            
            duration = time.time() - start_time
            logger.error(
                "WorkflowRunner failed (runner=%s, workflow=%s, duration=%.2fs): %s",
                self.runner_uuid,
                self._workflow_id,
                duration,
                e,
                exc_info=True,
            )
            raise

    async def _execute_standalone(self) -> list[TaskResult]:
        """Execute a single standalone task without graph overhead.
        
        This is the fast path for Standalone-Tasks (REQ-019).
        Directly executes the task without building dependency graph.
        
        Returns:
            List with single TaskResult
            
        Note:
            In mock mode (no executor configured), returns a placeholder result.
        """
        task_ctx = self.ctx.tasks[0]
        task_id = task_ctx.task_id
        
        logger.info(
            "Standalone execution (task=%s, workflow=%s)",
            task_id,
            self._workflow_id,
        )
        
        # Check if we have full executor capabilities
        if (
            self._opencode_client
            and self._session_strategy
            and self._git_manager
        ):
            # Full execution with OpenCode and Git
            return await self._execute_standalone_full(task_id, task_ctx)
        else:
            # Mock execution for testing
            return await self._execute_standalone_mock(task_id, task_ctx)

    async def _execute_standalone_full(
        self,
        task_id: UUID,
        task_ctx: "PreparedExecutionContext",
    ) -> list[TaskResult]:
        """Full standalone execution with OpenCode and Git.
        
        Args:
            task_id: Task to execute
            task_ctx: Task context with worktree info
            
        Returns:
            List with single TaskResult
        """
        # Initialize executor for single task
        self._executor = WorkflowExecutor(
            opencode_client=self._opencode_client,
            session_strategy=self._session_strategy,
            git_manager=self._git_manager,
        )
        
        # Create minimal graph for single task
        graph = DependencyGraph(
            nodes={task_id},
            edges={task_id: []},
        )
        
        # Execute via WorkflowExecutor (reuses session management)
        return await self._executor.execute(self.ctx, graph)

    async def _execute_standalone_mock(
        self,
        task_id: UUID,
        task_ctx: "PreparedExecutionContext",
    ) -> list[TaskResult]:
        """Mock standalone execution for testing.
        
        Args:
            task_id: Task to execute
            task_ctx: Task context with worktree info
            
        Returns:
            List with single TaskResult (placeholder)
        """
        logger.warning(
            "Standalone mock execution (task=%s, workflow=%s)",
            task_id,
            self._workflow_id,
        )
        
        # Simulate async work
        await asyncio.sleep(0)
        
        from execqueue.runner.workflow_executor import TaskResult

        commit_sha = getattr(task_ctx, "commit_sha", None)
        if commit_sha is None:
            commit_sha = getattr(task_ctx, "commit_sha_before", None)

        result = TaskResult(
            task_id=task_id,
            status="DONE",
            worktree_path=task_ctx.worktree_path,
            commit_sha=commit_sha,
            duration_seconds=0.0,
        )

        session = create_session()
        try:
            task_exists = session.get(Task, task_id) is not None
            if not task_exists:
                logger.info(
                    "Standalone mock execution has no persisted task for %s; "
                    "returning in-memory result only",
                    task_id,
                )
                return [result]

            try:
                claim_task(session, task_id, self.runner_uuid)
                session.commit()
            except ClaimFailedError:
                session.rollback()
                logger.warning(
                    "Standalone mock execution could not claim task %s for runner %s",
                    task_id,
                    self.runner_uuid,
                )
                raise

            ResultHandler(session).persist_results(
                self._workflow_id,
                [result],
            )
        finally:
            session.close()

        return [result]

    async def _execute_with_graph(self) -> list[TaskResult]:
        """Execute multi-task workflow with dependency graph.
        
        Uses full WorkflowExecutor for proper dependency resolution,
        batch execution, and session management.
        
        Returns:
            List of TaskResult for all tasks
            
        Note:
            Handles cycle detection and returns empty list if cycle found.
        """
        # Build dependency graph from context
        graph = DependencyGraph.from_context(self.ctx)
        
        # Check for cycles before execution
        if graph.detect_cycles():
            logger.error(
                "Cycle detected in workflow %s, aborting execution",
                self._workflow_id,
            )
            return []
        
        # Check if we have full executor capabilities
        if (
            self._opencode_client
            and self._session_strategy
            and self._git_manager
        ):
            # Full execution with OpenCode and Git
            return await self._execute_with_graph_full(graph)
        else:
            # Mock execution for testing
            return await self._execute_with_graph_mock(graph)

    async def _execute_with_graph_full(
        self,
        graph: DependencyGraph,
    ) -> list[TaskResult]:
        """Full multi-task execution with WorkflowExecutor.
        
        Args:
            graph: DependencyGraph for the workflow
            
        Returns:
            List of TaskResult for all tasks
        """
        # Initialize executor
        self._executor = WorkflowExecutor(
            opencode_client=self._opencode_client,
            session_strategy=self._session_strategy,
            git_manager=self._git_manager,
        )
        
        # Execute workflow via WorkflowExecutor
        return await self._executor.execute(self.ctx, graph)

    async def _execute_with_graph_mock(
        self,
        graph: DependencyGraph,
    ) -> list[TaskResult]:
        """Mock multi-task execution for testing.
        
        Args:
            graph: DependencyGraph for the workflow
            
        Returns:
            List of TaskResult (placeholders)
        """
        logger.warning(
            "Multi-task mock execution (workflow=%s, tasks=%d)",
            self._workflow_id,
            len(self.ctx.tasks),
        )
        
        from execqueue.runner.workflow_executor import TaskResult
        
        results = []
        for task_ctx in self.ctx.tasks:
            # Simulate async work
            await asyncio.sleep(0)
            
            results.append(
                TaskResult(
                    task_id=task_ctx.task_id,
                    status="DONE",
                    worktree_path=task_ctx.worktree_path,
                    commit_sha=task_ctx.commit_sha,
                    duration_seconds=0.0,
                )
            )
        
        return results

    @property
    def results(self) -> list[TaskResult]:
        """Get execution results.
        
        Returns:
            List of TaskResult from execution
        """
        return self._results

    @property
    def workflow_id(self) -> UUID:
        """Get workflow ID.
        
        Returns:
            Workflow UUID
        """
        return self._workflow_id

    @property
    def is_complete(self) -> bool:
        """Check if runner has completed execution.
        
        Returns:
            True if run() has been called and completed
        """
        return len(self._results) > 0 or self.ctx.finished_at is not None
