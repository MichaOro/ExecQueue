"""Runner entry point for REQ-012 task execution lifecycle.

This module provides the main runner entry point that can be used for:
- Polling-based task discovery and claiming
- Event-driven task execution start

The runner implements the REQ-012-02 claim semantics:
- Atomically claims prepared tasks
- Creates TaskExecution records
- Sets Task.status to QUEUED (not IN_PROGRESS yet)
- IN_PROGRESS is set only after successful Prompt Dispatch (future package)
"""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from execqueue.db.session import get_db_session
from execqueue.db.models import Task
from execqueue.orchestrator.workflow_models import Workflow
from execqueue.opencode.client import OpenCodeClient
from execqueue.runner.config import RunnerConfig
from execqueue.runner.dispatch import PromptDispatcher
from execqueue.runner.polling import poll_and_claim_tasks
from execqueue.runner.recovery import RecoveryService
from execqueue.runner.result_inspector import inspect_task_result, InspectionResult
from execqueue.runner.validator import Validator
from execqueue.runner.watchdog import Watchdog
from execqueue.runner.validation_pipeline import (
    ValidationPipeline,
    ValidatorRegistry,
    AggregationStrategy,
)
from execqueue.runner.validation_models import ValidationStatus
from execqueue.runner.commit_adopter import adopt_commit_with_lifecycle
from execqueue.runner.worktree_cleanup import WorktreeCleanupService
from execqueue.runner.worktree_manager import GitWorktreeManager
from execqueue.models.enums import ExecutionStatus, EventType
from execqueue.models.task_execution import TaskExecution
from execqueue.orchestrator.models import PreparedExecutionContext

logger = logging.getLogger(__name__)


class Runner:
    """Task execution runner for REQ-012 with REQ-021 integration.

    The runner polls for prepared tasks, claims them atomically, and
    processes them according to the REQ-012 lifecycle with REQ-021
    validation and commit adoption support.

    Attributes:
        config: Runner configuration
        _running: Internal flag indicating if runner is running
        _validator: Optional validator for execution results
        _validation_pipeline: Optional validation pipeline for multiple validators
        _worktree_cleanup: Worktree cleanup service for REQ-021
        _watchdog: Optional watchdog for session keep-alive
    """

    def __init__(
        self,
        config: RunnerConfig | None = None,
        validator: Validator | None = None,
        opencode_client: OpenCodeClient | None = None,
        worktree_root: str | None = None,
        require_validation: bool = True,
    ):
        """Initialize the runner with REQ-021 integration.

        Args:
            config: Runner configuration. If None, creates default config.
            validator: Optional validator for execution results.
                      If None, no validation is performed.
            opencode_client: Optional OpenCode client. If None, creates default client.
            worktree_root: Root directory for worktrees (for cleanup service).
                          If None, cleanup is disabled.
            require_validation: If True (default), block adoption on validation failure.
        """
        self.config = config or RunnerConfig.create_default()
        self._validator = validator
        self._validation_pipeline: ValidationPipeline | None = None
        self._require_validation = require_validation
        
        # Initialize validation pipeline if validator is provided or enabled in config
        if validator or self.config.validation_enabled:
            validators = [validator] if validator else []
            self._validation_pipeline = ValidationPipeline(
                validators=validators,
                aggregation=AggregationStrategy.all_passed,
                fail_fast=self.config.validation_fail_fast,
            )
        
        # Initialize worktree cleanup service based on config
        self._worktree_cleanup: WorktreeCleanupService | None = None
        if self.config.worktree_cleanup_enabled:
            worktree_root = worktree_root or self.config.worktree_root
            self._worktree_cleanup = WorktreeCleanupService(
                worktree_root=worktree_root,
                max_retries=self.config.worktree_cleanup_max_retries,
                force_cleanup=self.config.worktree_cleanup_force,
            )
        
        # Initialize GitWorktreeManager for REQ-021 metadata management
        self._worktree_manager = GitWorktreeManager(
            worktree_root=self.config.worktree_root,
            max_concurrent=self.config.worktree_max_concurrent,
        )
        
        self._watchdog = Watchdog(self.config)
        self._opencode_client = opencode_client or OpenCodeClient()
        self._dispatcher = PromptDispatcher(self._opencode_client)
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the runner's main loop and watchdog."""
        if self._running:
            logger.warning("Runner is already running")
            return

        self._running = True
        logger.info(
            f"Starting runner {self.config.runner_id} with "
            f"poll_interval={self.config.poll_interval_seconds}s, "
            f"batch_size={self.config.batch_size}"
        )

        # Start watchdog (no-op if disabled or no session_id)
        await self._watchdog.start()

        try:
            while self._running:
                await self._poll_cycle()
                await asyncio.sleep(self.config.poll_interval_seconds)
        except asyncio.CancelledError:
            logger.info("Runner received cancellation signal")
        finally:
            self._running = False
            logger.info(f"Runner {self.config.runner_id} stopped")

    async def _poll_cycle(self):
        """Execute one poll cycle: discover and claim tasks."""
        async with get_db_session() as session:
            try:
                executions = poll_and_claim_tasks(
                    session, self.config.runner_id, self.config.batch_size
                )

                for execution in executions:
                    await self._process_execution(session, execution)

            except Exception as e:
                logger.error(f"Error during poll cycle: {e}", exc_info=True)

    async def _process_execution(
        self, session: Session, execution: TaskExecution
    ):
        """Process a claimed execution with REQ-021 lifecycle.

        This method implements the full execution lifecycle:
        1. Run execution (placeholder for actual work)
        2. Use ExecutionChain to coordinate validation → adoption → cleanup

        Args:
            session: Database session
            execution: The claimed TaskExecution
        """
        logger.info(
            f"Processing execution {execution.id} for task {execution.task_id} "
            f"(status: {execution.status})"
        )

        # Record activity for watchdog (resets idle timer)
        self._watchdog.record_activity()

        # TODO: Implement actual execution logic
        # This is where the runner would:
        # 1. Set status to DISPATCHING
        # 2. Dispatch prompt to OpenCode
        # 3. Set status to IN_PROGRESS after successful dispatch
        # 4. Handle SSE events, result inspection, etc.
        # (These are covered in subsequent REQ-012 packages)

        # For now, check if execution is already done (simulated)
        if execution.status != ExecutionStatus.DONE.value:
            logger.info(
                f"Execution {execution.id} not yet complete, skipping adoption",
                extra={"execution_id": str(execution.id), "status": execution.status}
            )
            return

        # Use ExecutionChain to coordinate the complete REQ-021 workflow
        if self._validation_pipeline:
            from execqueue.runner.execution_chain import ExecutionChain
            
            execution_chain = ExecutionChain(
                worktree_root=self.config.worktree_root,
                target_branch=self.config.adoption_target_branch,
                max_retries=self.config.worktree_cleanup_max_retries,
                force_cleanup=self.config.worktree_cleanup_force,
            )
            
            try:
                success = await execution_chain.execute(
                    session=session,
                    execution=execution,
                    validation_pipeline=self._validation_pipeline,
                    validation_commands=self.config.adoption_validation_commands,
                )
                
                if success:
                    logger.info(
                        f"Execution chain completed successfully for execution {execution.id}",
                        extra={"execution_id": str(execution.id)}
                    )
                else:
                    logger.warning(
                        f"Execution chain completed with issues for execution {execution.id}",
                        extra={"execution_id": str(execution.id)}
                    )
                    
            except Exception as e:
                logger.error(
                    f"Execution chain failed for execution {execution.id}: {e}",
                    extra={"execution_id": str(execution.id)},
                    exc_info=True,
                )
        else:
            logger.info(
                f"No validation pipeline configured, skipping execution chain for execution {execution.id}",
                extra={"execution_id": str(execution.id)}
            )





    async def stop(self):
        """Stop the runner and watchdog gracefully."""
        logger.info(f"Stopping runner {self.config.runner_id}...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Stop watchdog (idempotent)
        await self._watchdog.stop()

    async def initialize_execution(
        self, context: PreparedExecutionContext
    ) -> TaskExecution | None:
        """Initialize a task execution from a prepared context.

        This method implements the REQ-012 initialization flow:
        1. Claim the task (creates TaskExecution with status=QUEUED)
        2. Initialize OpenCode session
        3. Configure watchdog with session_id
        4. Set status to IN_PROGRESS (without sending prompt)

        Args:
            context: PreparedExecutionContext from orchestrator

        Returns:
            The initialized TaskExecution, or None if initialization failed
        """
        from execqueue.runner.claim import claim_task

        correlation_id = context.correlation_id or "unknown"
        logger.info(
            f"Initializing execution for task {context.task_number}, "
            f"context version {context.version}",
            extra={"correlation_id": correlation_id, "task_id": str(context.task_id)},
        )

        async with get_db_session() as session:
            try:
                # Step 1: Claim the task (creates TaskExecution with status=QUEUED)
                # context.task_id is already a UUID, pass it directly
                execution = claim_task(session, context.task_id, self.config.runner_id)
                
                logger.info(
                    f"Claimed task {context.task_number}, execution {execution.id} in QUEUED state",
                    extra={"correlation_id": correlation_id, "execution_id": str(execution.id)},
                )

                # Step 2: Initialize OpenCode session (sets status to IN_PROGRESS)
                execution = await self._dispatcher.initialize_session(
                    session, execution.id, context
                )
                
                logger.info(
                    f"Session initialized for execution {execution.id}, "
                    f"session_id: {execution.opencode_session_id}",
                    extra={"correlation_id": correlation_id, "execution_id": str(execution.id)},
                )

                # Step 3: Configure watchdog with session_id
                self._watchdog.set_session_id(execution.opencode_session_id)
                
                # Start watchdog if enabled (it will only start if session_id is set)
                if self.config.watchdog_enabled and not self._watchdog.is_running:
                    await self._watchdog.start()
                    logger.info(
                        f"Watchdog started for session {execution.opencode_session_id}",
                        extra={"correlation_id": correlation_id},
                    )

                # Step 4: Record initial activity for watchdog
                self._watchdog.record_activity()

                session.commit()

                logger.info(
                    f"Execution {execution.id} successfully initialized to IN_PROGRESS",
                    extra={
                        "correlation_id": correlation_id,
                        "execution_id": str(execution.id),
                        "status": execution.status,
                    },
                )

                return execution

            except Exception as e:
                logger.error(
                    f"Failed to initialize execution for task {context.task_number}: {e}",
                    extra={
                        "correlation_id": correlation_id,
                        "task_id": str(context.task_id),
                    },
                    exc_info=True,
                )
                return None

    async def claim_single_task(self, task_id: str) -> TaskExecution | None:
        """Claim a specific task (for event-driven usage).

        Args:
            task_id: UUID of the task to claim

        Returns:
            The created TaskExecution if successful, None otherwise
        """
        async with get_db_session() as session:
            try:
                from execqueue.runner.claim import claim_task

                execution = claim_task(session, task_id, self.config.runner_id)
                await self._process_execution(session, execution)
                return execution
            except Exception as e:
                logger.warning(f"Failed to claim task {task_id}: {e}")
                return None


@asynccontextmanager
async def runner_lifecycle(config: RunnerConfig | None = None):
    """Context manager for runner lifecycle management.

    Usage:
        async with runner_lifecycle() as runner:
            await runner.start()
    """
    runner = Runner(config)

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler():
        asyncio.create_task(runner.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        yield runner
    finally:
        await runner.stop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


async def main():
    """Main entry point for the runner."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    async with runner_lifecycle() as runner:
        await runner.start()


if __name__ == "__main__":
    asyncio.run(main())
