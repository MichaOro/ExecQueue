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
from uuid import uuid4

from sqlalchemy.orm import Session

from execqueue.db.session import get_db_session
from execqueue.runner.config import RunnerConfig
from execqueue.runner.polling import poll_and_claim_tasks
from execqueue.runner.validator import Validator
from execqueue.runner.watchdog import Watchdog
from execqueue.models.task_execution import TaskExecution

logger = logging.getLogger(__name__)


class Runner:
    """Task execution runner for REQ-012.

    The runner polls for prepared tasks, claims them atomically, and
    processes them according to the REQ-012 lifecycle.

    Attributes:
        config: Runner configuration
        _running: Internal flag indicating if runner is running
        _validator: Optional validator for execution results
        _watchdog: Optional watchdog for session keep-alive
    """

    def __init__(
        self,
        config: RunnerConfig | None = None,
        validator: Validator | None = None,
    ):
        """Initialize the runner.

        Args:
            config: Runner configuration. If None, creates default config.
            validator: Optional validator for execution results.
                      If None, no validation is performed.
        """
        self.config = config or RunnerConfig.create_default()
        self._validator = validator
        self._watchdog = Watchdog(self.config)
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
        """Process a claimed execution.

        This is a placeholder for future processing logic.
        Currently, it only logs the claimed execution and optionally
        runs validation.

        Args:
            session: Database session
            execution: The claimed TaskExecution
        """
        logger.info(
            f"Processing execution {execution.id} for task {execution.task_id} "
            f"(status: {execution.status})"
        )

        # TODO: Implement actual processing logic
        # This is where the runner would:
        # 1. Set status to DISPATCHING
        # 2. Dispatch prompt to OpenCode
        # 3. Set status to IN_PROGRESS after successful dispatch
        # 4. Handle SSE events, result inspection, etc.
        # (These are covered in subsequent REQ-012 packages)

        # Record activity for watchdog (resets idle timer)
        self._watchdog.record_activity()

        # Run validator if configured (only logs, does not affect status)
        if self._validator:
            await self._run_validator(execution)

    async def _run_validator(self, execution: TaskExecution) -> None:
        """Run the validator on an execution and log the result.

        The validator result is only logged and does not affect the
        execution status. Exceptions are caught and logged.

        Args:
            execution: The TaskExecution to validate
        """
        try:
            result = await self._validator.validate(execution)
            if result:
                logger.info(
                    f"Validation passed for execution {execution.id}"
                )
            else:
                logger.warning(
                    f"Validation failed for execution {execution.id}"
                )
        except Exception as e:
            logger.warning(
                f"Validator exception for execution {execution.id}: {e}",
                exc_info=True,
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
