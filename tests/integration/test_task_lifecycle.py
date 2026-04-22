import pytest
from unittest.mock import patch
from sqlmodel import Session, select
from execqueue.scheduler.runner import run_next_task
from execqueue.services.queue_service import enqueue_requirement
from execqueue.models.task import Task
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage


def _mock_opencode_done():
    """Helper to create a mock that returns 'done'."""
    return type(
        "MockResult",
        (),
        {
            "status": "completed",
            "raw_output": '{"status": "done", "summary": "Completed successfully."}',
            "summary": "Completed successfully.",
        },
    )()


def _mock_opencode_not_done():
    """Helper to create a mock that returns 'not_done'."""
    return type(
        "MockResult",
        (),
        {
            "status": "completed",
            "raw_output": '{"status": "not_done", "summary": "Failed to complete."}',
            "summary": "Failed to complete.",
        },
    )()


class TestTaskLifecycle:
    """Integration tests for complete task lifecycle flows."""

    def test_full_flow_requirement_to_done(self, db_session: Session, sample_requirement):
        """Test: Complete flow from Requirement to Task done."""
        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 1
        assert tasks[0].status == "queued"

        refreshed_requirement = db_session.get(Requirement, sample_requirement.id)
        assert refreshed_requirement.status == "planned"

        result = run_next_task(db_session)

        assert result is not None
        assert result.status == "done"

        final_requirement = db_session.get(Requirement, sample_requirement.id)
        assert final_requirement.status == "done"

    def test_full_flow_with_work_packages(self, db_session: Session, sample_requirement):
        """Test: Complete flow with multiple WorkPackages."""
        work_packages = [
            WorkPackage(
                requirement_id=sample_requirement.id,
                title=f"WP {i}",
                description=f"Description {i}",
                execution_order=i,
            )
            for i in range(2)
        ]
        db_session.add_all(work_packages)
        db_session.commit()

        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 2

        for wp in work_packages:
            refreshed_wp = db_session.get(WorkPackage, wp.id)
            assert refreshed_wp.status == "backlog"

        run_next_task(db_session)
        run_next_task(db_session)

        for wp in work_packages:
            final_wp = db_session.get(WorkPackage, wp.id)
            assert final_wp.status == "done"

        final_requirement = db_session.get(Requirement, sample_requirement.id)
        assert final_requirement.status == "done"

    def test_retry_flow_multiple_iterations(self, db_session: Session, sample_task):
        """Test: Retry flow over multiple iterations."""
        sample_task.max_retries = 3
        db_session.add(sample_task)
        db_session.commit()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            side_effect=[_mock_opencode_not_done(), _mock_opencode_not_done(), _mock_opencode_done()],
        ):
            result1 = run_next_task(db_session)
            assert result1.status == "queued"
            assert result1.retry_count == 1

            result2 = run_next_task(db_session)
            assert result2.status == "queued"
            assert result2.retry_count == 2

            result3 = run_next_task(db_session)
            assert result3.status == "done"
            assert result3.retry_count == 2

    def test_failed_task_after_max_retries(self, db_session: Session, sample_task):
        """Test: Task marked as failed after exhausting max_retries."""
        sample_task.retry_count = sample_task.max_retries - 1
        db_session.add(sample_task)
        db_session.commit()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=_mock_opencode_not_done(),
        ):
            result = run_next_task(db_session)

        assert result.status == "failed"
        assert result.retry_count == sample_task.max_retries

    def test_status_transition_validation(self, db_session: Session):
        """Test: Tasks in in_progress state are skipped."""
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

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=_mock_opencode_done(),
        ):
            result = run_next_task(db_session)

        assert result is not None
        assert result.id == task2.id
        assert result.status == "done"

    def test_work_package_requirement_status_sync(self, db_session: Session, sample_requirement):
        """Test: Requirement status updates after all WorkPackages are done."""
        work_packages = [
            WorkPackage(
                requirement_id=sample_requirement.id,
                title=f"WP {i}",
                description=f"Description {i}",
                execution_order=i,
            )
            for i in range(3)
        ]
        db_session.add_all(work_packages)
        db_session.commit()

        enqueue_requirement(sample_requirement.id, db_session)

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=_mock_opencode_done(),
        ):
            run_next_task(db_session)

            mid_requirement = db_session.get(Requirement, sample_requirement.id)
            assert mid_requirement.status == "planned"

            run_next_task(db_session)
            run_next_task(db_session)

            final_requirement = db_session.get(Requirement, sample_requirement.id)
            assert final_requirement.status == "done"

    def test_task_last_result_persisted(self, db_session: Session, sample_task):
        """Test: Task.last_result is persisted after execution."""
        expected_output = '{"status": "done", "summary": "Test summary"}'

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=type(
                "MockResult",
                (),
                {
                    "status": "completed",
                    "raw_output": expected_output,
                    "summary": "Test summary",
                },
            )(),
        ):
            run_next_task(db_session)

        refreshed_task = db_session.get(Task, sample_task.id)
        assert refreshed_task.last_result == expected_output

    def test_task_updated_at_changes(self, db_session: Session, sample_task):
        """Test: Task.updated_at is updated after execution."""
        from datetime import datetime, timedelta

        initial_updated_at = sample_task.updated_at

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=_mock_opencode_done(),
        ):
            run_next_task(db_session)

        refreshed_task = db_session.get(Task, sample_task.id)
        assert refreshed_task.updated_at > initial_updated_at - timedelta(seconds=1)
