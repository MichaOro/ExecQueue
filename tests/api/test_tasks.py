import pytest
from sqlmodel import select

from execqueue.models.task import Task
from execqueue.models.work_package import WorkPackage
from tests.conftest import TEST_QUEUE_PREFIX


class TestTasksAPI:
    """API tests for tasks endpoint."""

    def test_get_tasks_empty(self, api_client):
        """Test: GET /tasks returns empty list."""
        response = api_client.get("/tasks")

        assert response.status_code == 200
        assert response.json() == []

    def test_post_task(self, api_client, session_with_data):
        """Test: POST /tasks creates a task."""
        wp_id = session_with_data.exec(select(WorkPackage.id).limit(1)).first()

        payload = {
            "source_type": "work_package",
            "source_id": wp_id,
            "title": "Test Task",
            "prompt": "Test prompt",
            "verification_prompt": "Verify this",
            "execution_order": 1,
            "max_retries": 5,
        }

        response = api_client.post("/tasks", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == f"{TEST_QUEUE_PREFIX}Test Task"
        assert data["source_type"] == "work_package"
        assert data["status"] == "queued"
        assert "id" in data

    def test_get_tasks_with_data(self, api_client, session_with_data):
        """Test: GET /tasks returns created tasks."""
        response = api_client.get("/tasks")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_post_task_minimal_payload(self, api_client, session_with_data):
        """Test: POST /tasks with minimal required fields."""
        wp_id = session_with_data.exec(select(WorkPackage.id).limit(1)).first()

        payload = {
            "source_type": "work_package",
            "source_id": wp_id,
            "title": "Minimal Task",
            "prompt": "Minimal prompt",
        }

        response = api_client.post("/tasks", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == f"{TEST_QUEUE_PREFIX}Minimal Task"
        assert data["execution_order"] == 0
        assert data["max_retries"] == 5
        assert data["status"] == "queued"

    def test_post_task_start(self, api_client, session_with_data):
        """Test: POST /tasks/{id}/start changes status to in_progress."""
        task = session_with_data.exec(select(Task).limit(1)).first()

        response = api_client.post(f"/tasks/{task.id}/start")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"

    def test_post_task_start_not_found(self, api_client):
        """Test: POST /tasks/{id}/start returns 404 for non-existent task."""
        response = api_client.post("/tasks/9999/start")

        assert response.status_code == 404

    def test_post_task_done(self, api_client, session_with_data):
        """Test: POST /tasks/{id}/done changes status to done."""
        task = session_with_data.exec(select(Task).limit(1)).first()

        response = api_client.post(f"/tasks/{task.id}/done")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"

    def test_post_task_done_not_found(self, api_client):
        """Test: POST /tasks/{id}/done returns 404 for non-existent task."""
        response = api_client.post("/tasks/9999/done")

        assert response.status_code == 404

    def test_post_task_fail(self, api_client, session_with_data):
        """Test: POST /tasks/{id}/fail changes status to failed."""
        task = session_with_data.exec(select(Task).limit(1)).first()

        response = api_client.post(f"/tasks/{task.id}/fail?result=Error occurred")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["last_result"] == "Error occurred"
        assert data["retry_count"] == 1

    def test_post_task_fail_not_found(self, api_client):
        """Test: POST /tasks/{id}/fail returns 404 for non-existent task."""
        response = api_client.post("/tasks/9999/fail?result=Error")

        assert response.status_code == 404
