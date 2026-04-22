import pytest
from unittest.mock import patch
from sqlmodel import Session, select
from execqueue.scheduler.runner import run_next_task, run_task, get_next_queued_task
from execqueue.models.task import Task
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage


class TestRunNextTask:
    """Integration tests for run_next_task function."""

    def test_run_next_task_successful(self, db_session: Session, sample_task):
        """Test: run_next_task with successful completion."""
        result = run_next_task(db_session)

        assert result is not None
        assert result.id == sample_task.id
        assert result.status == "done"
        assert result.last_result is not None
        assert result.retry_count == 0

        refreshed_task = db_session.get(Task, sample_task.id)
        assert refreshed_task.status == "done"

    def test_run_next_task_retry(self, db_session: Session, sample_task, mocker):
        """Test: run_next_task retries on failure."""
        mocker.patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=type(
                "MockResult",
                (),
                {
                    "status": "completed",
                    "raw_output": '{"status": "not_done", "summary": "Failed"}',
                    "summary": "Failed",
                },
            )(),
        )

        result = run_next_task(db_session)

        assert result is not None
        assert result.status == "queued"
        assert result.retry_count == 1

    def test_run_next_task_max_retries(self, db_session: Session, sample_task):
        """Test: run_next_task marks task as failed after max_retries."""
        sample_task.retry_count = sample_task.max_retries - 1
        db_session.add(sample_task)
        db_session.commit()

        result = run_next_task(db_session)

        assert result is not None
        assert result.status == "failed"
        assert result.retry_count == sample_task.max_retries

    def test_run_next_task_empty_queue(self, db_session: Session):
        """Test: run_next_task returns None when queue is empty."""
        result = run_next_task(db_session)

        assert result is None

    def test_run_next_task_execution_order(self, db_session: Session, sample_task_queue):
        """Test: run_next_task processes tasks in execution_order."""
        result1 = run_next_task(db_session)
        result2 = run_next_task(db_session)
        result3 = run_next_task(db_session)

        assert result1.execution_order == 1
        assert result2.execution_order == 2
        assert result3.execution_order == 3

    def test_run_next_task_skips_in_progress(self, db_session: Session):
        """Test: run_next_task skips tasks that are in_progress."""
        task1 = Task(
            source_type="requirement",
            source_id=1,
            title="Task 1",
            prompt="Prompt 1",
            status="in_progress",
            execution_order=1,
        )
        task2 = Task(
            source_type="requirement",
            source_id=1,
            title="Task 2",
            prompt="Prompt 2",
            status="queued",
            execution_order=2,
        )
        db_session.add_all([task1, task2])
        db_session.commit()

        result = run_next_task(db_session)

        assert result is not None
        assert result.id == task2.id


class TestRunTask:
    """Integration tests for run_task function."""

    def test_run_task_not_found(self, db_session: Session):
        """Test: run_task raises ValueError for non-existent task."""
        with pytest.raises(ValueError, match="Task 9999 not found"):
            run_task(9999, db_session)

    def test_run_task_not_queued(self, db_session: Session, sample_task):
        """Test: run_task raises ValueError for non-queued task."""
        sample_task.status = "done"
        db_session.add(sample_task)
        db_session.commit()

        with pytest.raises(ValueError, match="is not queued"):
            run_task(sample_task.id, db_session)

    def test_run_task_successful(self, db_session: Session, sample_task):
        """Test: run_task marks task as done on success."""
        result = run_task(sample_task.id, db_session)

        assert result.status == "done"

        refreshed_task = db_session.get(Task, sample_task.id)
        assert refreshed_task.status == "done"
        assert refreshed_task.last_result is not None


class TestGetNextQueuedTask:
    """Integration tests for get_next_queued_task function."""

    def test_get_next_queued_task_returns_oldest(self, db_session: Session):
        """Test: get_next_queued_task returns task with lowest execution_order."""
        task1 = Task(
            source_type="requirement",
            source_id=1,
            title="Task 1",
            prompt="Prompt 1",
            status="queued",
            execution_order=5,
        )
        task2 = Task(
            source_type="requirement",
            source_id=1,
            title="Task 2",
            prompt="Prompt 2",
            status="queued",
            execution_order=2,
        )
        task3 = Task(
            source_type="requirement",
            source_id=1,
            title="Task 3",
            prompt="Prompt 3",
            status="queued",
            execution_order=8,
        )
        db_session.add_all([task1, task2, task3])
        db_session.commit()

        result = get_next_queued_task(db_session)

        assert result is not None
        assert result.id == task2.id

    def test_get_next_queued_task_empty(self, db_session: Session):
        """Test: get_next_queued_task returns None when no queued tasks."""
        result = get_next_queued_task(db_session)

        assert result is None

    def test_get_next_queued_task_ignores_done(self, db_session: Session):
        """Test: get_next_queued_task ignores done tasks."""
        task = Task(
            source_type="requirement",
            source_id=1,
            title="Task 1",
            prompt="Prompt 1",
            status="done",
            execution_order=1,
        )
        db_session.add(task)
        db_session.commit()

        result = get_next_queued_task(db_session)

        assert result is None
