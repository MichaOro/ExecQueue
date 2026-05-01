"""Workflow execution engine for REQ-016."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID
    from execqueue.opencode.client import OpenCodeClient
    from execqueue.runner.graph import DependencyGraph
    from execqueue.runner.session_strategy import HybridSessionStrategy, SessionPlan
    from execqueue.runner.git_workflow import GitWorkflowManager
    from execqueue.orchestrator.workflow_models import WorkflowContext

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Result of a single task execution.

    Attributes:
        task_id: Task identifier
        status: DONE / FAILED / RETRY
        commit_sha: Commit SHA after execution (if applicable)
        worktree_path: Worktree path used
        opencode_session_id: Session ID used
        result_payload: Raw result from OpenCode
        duration_seconds: Execution duration
        error_message: Error message if failed
    """

    task_id: UUID
    status: str  # 'DONE', 'FAILED', 'RETRY'
    commit_sha: str | None = None
    worktree_path: str | None = None
    opencode_session_id: str | None = None
    result_payload: dict | None = None
    duration_seconds: float | None = None
    error_message: str | None = None


@dataclass
class BatchResult:
    """Result of a batch execution.

    Attributes:
        batch_index: Batch number (0-indexed)
        task_results: List of TaskResult for this batch
    """

    batch_index: int
    task_results: list[TaskResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if all tasks in batch succeeded."""
        return all(r.status == "DONE" for r in self.task_results)


class WorkflowExecutor:
    """Executes workflows with hybrid session strategy and Git integration.

    Usage:
        executor = WorkflowExecutor(opencode_client, strategy, git_manager)
        results = await executor.execute(workflow_context, graph)
    """

    def __init__(
        self,
        opencode_client: OpenCodeClient,
        session_strategy: HybridSessionStrategy,
        git_manager: GitWorkflowManager,
        task_timeout_seconds: int = 300,
        batch_timeout_seconds: int = 600,
    ):
        """Initialize executor.

        Args:
            opencode_client: OpenCode client for prompt dispatch
            session_strategy: Session strategy for hybrid execution
            git_manager: Git workflow manager for worktree/commit operations
            task_timeout_seconds: Timeout per task (default: 5 min)
            batch_timeout_seconds: Timeout per batch (default: 10 min)
        """
        self._client = opencode_client
        self._strategy = session_strategy
        self._git_manager = git_manager
        self._task_timeout = task_timeout_seconds
        self._batch_timeout = batch_timeout_seconds

    async def execute(
        self,
        ctx: WorkflowContext,
        graph: DependencyGraph,
    ) -> list[TaskResult]:
        """Execute a workflow.

        Args:
            ctx: WorkflowContext with tasks and dependencies
            graph: DependencyGraph built from ctx

        Returns:
            List of TaskResult for all tasks (may be partial if failures occur)

        Note:
            Session lifecycle:
            1. create_sessions() called before batch execution
            2. Batches executed sequentially
            3. cleanup_sessions() called after all batches (even on failure)
        """
        logger.info(f"Starting workflow execution {ctx.workflow_id}")

        # Step 1: Check for cycles
        if graph.detect_cycles():
            logger.error("Cycle detected in workflow dependencies")
            return []

        # Step 2: Build session plan
        sequential_paths = graph.get_sequential_paths()
        all_task_ids = list(ctx.dependencies.keys())

        session_plan = self._strategy.create_plan(
            sequential_paths, all_task_ids
        )

        # Step 3: Create sessions (before any execution)
        session_plan = await self._strategy.create_sessions(session_plan)

        # Step 4: Get batches from graph
        batches = graph.get_parallel_batches()
        if not batches and len(ctx.dependencies) > 0:
            logger.error("No batches returned, possible cycle or empty graph")
            await self._strategy.cleanup_sessions(session_plan)
            return []

        # Step 5: Execute batches sequentially
        all_results: list[TaskResult] = []
        workflow_failed = False

        try:
            for batch_idx, batch_tasks in enumerate(batches):
                logger.info(
                    f"Executing batch {batch_idx + 1}/{len(batches)} "
                    f"({len(batch_tasks)} tasks)"
                )

                batch_results = await asyncio.wait_for(
                    self._execute_batch(
                        batch_idx, batch_tasks, ctx, session_plan
                    ),
                    timeout=self._batch_timeout,
                )

                all_results.extend(batch_results.task_results)

                if not batch_results.success:
                    failed_count = sum(
                        1 for r in batch_results.task_results if r.status == "FAILED"
                    )
                    logger.warning(
                        f"Batch {batch_idx} had {failed_count} failures, "
                        f"continuing with next batch"
                    )
                    workflow_failed = True

        except asyncio.TimeoutError:
            logger.error(f"Batch execution timed out after {self._batch_timeout}s")
            workflow_failed = True

        finally:
            # Step 6: Cleanup sessions (always, even on failure)
            logger.info("Cleaning up sessions")
            await self._strategy.cleanup_sessions(session_plan)

        # Summary
        done_count = sum(1 for r in all_results if r.status == "DONE")
        failed_count = sum(1 for r in all_results if r.status == "FAILED")

        logger.info(
            f"Workflow execution complete: {done_count} done, {failed_count} failed"
        )

        return all_results

    async def _execute_batch(
        self,
        batch_idx: int,
        batch_tasks: list[UUID],
        ctx: WorkflowContext,
        session_plan: SessionPlan,
    ) -> BatchResult:
        """Execute a single batch of tasks in parallel.

        Args:
            batch_idx: Batch index
            batch_tasks: Task IDs in this batch
            ctx: WorkflowContext
            session_plan: Session plan with assignments

        Returns:
            BatchResult with all task results
        """
        logger.info(f"Starting batch {batch_idx} with {len(batch_tasks)} tasks")

        # Execute tasks in parallel within the batch
        tasks = [
            self._execute_single_task(task_id, ctx, session_plan)
            for task_id in batch_tasks
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_result = BatchResult(batch_index=batch_idx)

        for i, result in enumerate(results):
            task_id = batch_tasks[i]

            if isinstance(result, Exception):
                # Exception during execution
                batch_result.task_results.append(
                    TaskResult(
                        task_id=task_id,
                        status="FAILED",
                        error_message=str(result),
                    )
                )
            else:
                batch_result.task_results.append(result)

        success_count = sum(1 for r in batch_result.task_results if r.status == "DONE")
        logger.info(
            f"Batch {batch_idx} complete: {success_count}/{len(batch_tasks)} done"
        )

        return batch_result

    async def _execute_single_task(
        self,
        task_id: UUID,
        ctx: WorkflowContext,
        session_plan: SessionPlan,
    ) -> TaskResult:
        """Execute a single task.

        Args:
            task_id: Task to execute
            ctx: WorkflowContext
            session_plan: Session plan

        Returns:
            TaskResult
        """
        start_time = time.time()

        # Get session for this task
        session_id = session_plan.get_session_for_task(task_id)
        if not session_id:
            return TaskResult(
                task_id=task_id,
                status="FAILED",
                error_message=f"No session assigned for task {task_id}",
            )

        # Get task context
        task_ctx = None
        for task in ctx.tasks:
            if task.task_id == task_id:
                task_ctx = task
                break

        if not task_ctx:
            return TaskResult(
                task_id=task_id,
                status="FAILED",
                error_message=f"Task {task_id} not found in workflow context",
            )

        try:
            # Execute with timeout
            return await asyncio.wait_for(
                self._do_execute_task(task_id, task_ctx, session_id),
                timeout=self._task_timeout,
            )

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            logger.error(f"Task {task_id} timed out after {self._task_timeout}s")

            return TaskResult(
                task_id=task_id,
                status="FAILED",
                error_message=f"Task timed out after {self._task_timeout}s",
                duration_seconds=duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)

            return TaskResult(
                task_id=task_id,
                status="FAILED",
                error_message=str(e),
                duration_seconds=duration,
            )

    async def _do_execute_task(
        self,
        task_id: UUID,
        task_ctx: "PreparedExecutionContext",
        session_id: str,
    ) -> TaskResult:
        """Actually execute a task (extracted for timeout handling).

        Args:
            task_id: Task to execute
            task_ctx: Task context with worktree info
            session_id: Session ID to use

        Returns:
            TaskResult
        """
        start_time = time.time()

        # TODO: Implement actual prompt dispatch
        # This is where the runner would:
        # 1. Build prompt from task context
        # 2. Dispatch to OpenCode with session_id
        # 3. Wait for result (SSE or polling)
        # 4. Process result

        logger.info(f"Executing task {task_id} in session {session_id}")

        # Placeholder: Simulate execution
        # await self._client.dispatch_message(session_id, prompt)

        # If this is a write task, use git_manager for commits
        # if task_ctx.is_write_task:
        #     commit_sha = await self._git_manager.commit_changes(
        #         worktree_path=Path(task_ctx.worktree_path),
        #         message=f"Task {task_id} completed"
        #     )

        duration = time.time() - start_time

        return TaskResult(
            task_id=task_id,
            status="DONE",
            opencode_session_id=session_id,
            worktree_path=task_ctx.worktree_path,
            duration_seconds=duration,
        )
