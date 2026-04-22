import pytest
from unittest.mock import patch
from execqueue.models.task import Task


def mock_opencode_done():
    """Helper to create a mock that returns 'done'."""
    return type(
        "MockResult",
        (),
        {
            "status": "completed",
            "raw_output": '{"status": "done", "summary": "Completed."}',
            "summary": "Completed.",
        },
    )()


def mock_opencode_not_done():
    """Helper to create a mock that returns 'not_done'."""
    return type(
        "MockResult",
        (),
        {
            "status": "completed",
            "raw_output": '{"status": "not_done", "summary": "Failed."}',
            "summary": "Failed.",
        },
    )()


class TestRunnerAPI:
    """API tests for runner endpoint."""

    def test_run_next_empty_queue(self, api_client):
        """Test: POST /runner/run-next returns message when queue is empty."""
        response = api_client.post("/runner/run-next")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "No queued task available"

    def test_run_next_with_task(self, api_client, session_with_data):
        """Test: POST /runner/run-next processes a queued task."""
        from sqlmodel import select
        task = session_with_data.exec(select(Task).limit(1)).first()
        task.status = "queued"
        session_with_data.add(task)
        session_with_data.commit()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_done(),
        ):
            response = api_client.post("/runner/run-next")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Task processed"
        assert data["task_id"] == task.id
        assert data["status"] == "done"
        assert data["retry_count"] == 0

    def test_run_next_task_requeued_on_failure(self, api_client, session_with_data):
        """Test: POST /runner/run-next requeues task on failure."""
        from sqlmodel import select
        task = Task(
            source_type="requirement",
            source_id=1,
            title="Retry Task",
            prompt="Prompt",
            status="queued",
            execution_order=1,
            max_retries=3,
        )
        session_with_data.add(task)
        session_with_data.commit()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_not_done(),
        ):
            response = api_client.post("/runner/run-next")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["retry_count"] == 1

    def test_run_next_task_failed_after_max_retries(
        self, api_client, session_with_data
    ):
        """Test: POST /runner/run-next marks task as failed after max_retries."""
        task = Task(
            source_type="requirement",
            source_id=1,
            title="Max Retry Task",
            prompt="Prompt",
            status="queued",
            execution_order=1,
            max_retries=2,
            retry_count=1,
        )
        session_with_data.add(task)
        session_with_data.commit()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_not_done(),
        ):
            response = api_client.post("/runner/run-next")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["retry_count"] == 2

    def test_run_next_returns_task_details(self, api_client, session_with_data):
        """Test: POST /runner/run-next returns task source details."""
        from sqlmodel import select
        task = session_with_data.exec(select(Task).limit(1)).first()
        task.status = "queued"
        session_with_data.add(task)
        session_with_data.commit()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_done(),
        ):
            response = api_client.post("/runner/run-next")

        assert response.status_code == 200
        data = response.json()
        assert "source_type" in data
        assert "source_id" in data
        assert data["source_type"] == task.source_type
        assert data["source_id"] == task.source_id
