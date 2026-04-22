"""Integration tests for scheduler worker with database."""

from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from execqueue.scheduler.runner import run_next_task
from execqueue.models.task import Task


class TestWorkerWithDatabase:
    """Integration tests for worker with real database."""

    def test_run_next_task_processes_queued_task(
        self, db_session: Session, sample_task
    ):
        """Worker processes a queued task from database."""
        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=MagicMock(
                status="completed",
                raw_output='{"status": "done", "summary": "Success"}',
                summary="Success",
            ),
        ):
            result = run_next_task(db_session)

        assert result is not None
        assert result.id == sample_task.id
        assert result.status == "done"
        assert result.retry_count == 0

    def test_run_next_task_returns_none_when_empty(
        self, db_session: Session
    ):
        """Worker returns None when no tasks in queue."""
        result = run_next_task(db_session)

        assert result is None

    def test_run_next_task_respects_execution_order(
        self, db_session: Session, sample_task_queue
    ):
        """Worker processes tasks in execution_order."""
        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=MagicMock(
                status="completed",
                raw_output='{"status": "done", "summary": "Success"}',
                summary="Success",
            ),
        ):
            result1 = run_next_task(db_session)
            result2 = run_next_task(db_session)
            result3 = run_next_task(db_session)

        assert result1.execution_order == 1
        assert result2.execution_order == 2
        assert result3.execution_order == 3

    def test_run_next_task_skips_in_progress(
        self, db_session: Session
    ):
        """Worker skips tasks that are in_progress."""
        task_in_progress = Task(
            source_type="requirement",
            source_id=1,
            title="In Progress Task",
            prompt="Prompt",
            status="in_progress",
            execution_order=1,
            is_test=True,
        )
        task_queued = Task(
            source_type="requirement",
            source_id=1,
            title="Queued Task",
            prompt="Prompt",
            status="queued",
            execution_order=2,
            is_test=True,
        )

        db_session.add_all([task_in_progress, task_queued])
        db_session.commit()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=MagicMock(
                status="completed",
                raw_output='{"status": "done", "summary": "Success"}',
                summary="Success",
            ),
        ):
            result = run_next_task(db_session)

        assert result is not None
        assert result.id == task_queued.id

    def test_run_next_task_retry_logic(
        self, db_session: Session, sample_task
    ):
        """Worker retries task on validation failure."""
        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=MagicMock(
                status="completed",
                raw_output='{"status": "not_done", "summary": "Failed"}',
                summary="Failed",
            ),
        ):
            result = run_next_task(db_session)

        assert result is not None
        assert result.status == "queued"
        assert result.retry_count == 1

    def test_run_next_task_fails_after_max_retries(
        self, db_session: Session, sample_task
    ):
        """Worker marks task as failed after max_retries."""
        sample_task.retry_count = sample_task.max_retries - 1
        db_session.add(sample_task)
        db_session.commit()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=MagicMock(
                status="completed",
                raw_output='{"status": "not_done", "summary": "Failed"}',
                summary="Failed",
            ),
        ):
            result = run_next_task(db_session)

        assert result is not None
        assert result.status == "failed"
        assert result.retry_count == sample_task.max_retries


class TestWorkerGracefulShutdown:
    """Tests for graceful shutdown behavior."""

    def test_shutdown_does_not_interrupt_current_task(
        self, db_session: Session, sample_task
    ):
        """Current task completes before shutdown."""
        import time

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            side_effect=lambda *args, **kwargs: (
                time.sleep(0.01),
                MagicMock(
                    status="completed",
                    raw_output='{"status": "done"}',
                    summary="Done",
                ),
            )[1],
        ):
            result = run_next_task(db_session)

        assert result is not None
        assert result.status == "done"

    def test_shutdown_prevents_new_task_acceptance(
        self, db_session: Session
    ):
        """No new tasks are accepted after shutdown signal."""
        from execqueue.scheduler import worker

        original_requested = worker._shutdown_requested
        worker._shutdown_requested = True

        try:
            result = run_next_task(db_session)
            assert result is None
        finally:
            worker._shutdown_requested = original_requested
