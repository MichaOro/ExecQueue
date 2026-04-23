"""
Tests for Queue-Steuerung API Endpoints.

Tests the new queue management endpoints for the orchestrated task system.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task


class TestQueueStatusEndpoints:
    """Tests for queue status and management endpoints."""

    def test_get_queue_status(self, client: TestClient, db_session: Session):
        """Test: GET /queue/status returns queue state."""
        response = client.get("/queue/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "queue_blocked" in data
        assert "parallel_task_count" in data
        assert "is_test_mode" in data

    def test_get_kanban_board(self, client: TestClient, db_session: Session):
        """Test: GET /queue/kanban returns Kanban overview."""
        response = client.get("/queue/kanban")
        
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "work_packages" in data
        assert "requirements" in data

    def test_get_valid_transitions(self, client: TestClient):
        """Test: GET /queue/valid-transitions returns valid status transitions."""
        response = client.get("/queue/valid-transitions")
        
        assert response.status_code == 200
        data = response.json()
        assert "backlog" in data
        assert "in_progress" in data
        assert "review" in data
        assert "done" in data
        assert "trash" in data


class TestTaskQueueStatusEndpoints:
    """Tests for task queue status update endpoints."""

    def test_update_task_queue_status_success(
        self, client: TestClient, db_session: Session, sample_task
    ):
        """Test: PATCH /queue/tasks/{id}/queue-status updates status."""
        payload = {"queue_status": "in_progress"}
        response = client.patch(
            f"/queue/tasks/{sample_task.id}/queue-status",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Task queue_status updated"
        assert data["task"]["queue_status"] == "in_progress"

    def test_update_task_queue_status_invalid_transition(
        self, client: TestClient, db_session: Session, sample_task
    ):
        """Test: PATCH rejects invalid status transitions."""
        payload = {"queue_status": "done"}  # Can't go directly from backlog to done
        response = client.patch(
            f"/queue/tasks/{sample_task.id}/queue-status",
            json=payload
        )
        
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_update_task_queue_status_not_found(self, client: TestClient):
        """Test: PATCH returns 404 for non-existent task."""
        payload = {"queue_status": "in_progress"}
        response = client.patch("/queue/tasks/99999/queue-status", json=payload)
        
        assert response.status_code == 404

    def test_update_task_block_queue(self, client: TestClient, db_session: Session, sample_task):
        """Test: PATCH /queue/tasks/{id}/block-queue toggles block flag."""
        payload = {"block_queue": True}
        response = client.patch(
            f"/queue/tasks/{sample_task.id}/block-queue",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Queue blocked"
        assert data["task"]["block_queue"] is True

    def test_update_task_schedulable(self, client: TestClient, db_session: Session, sample_task):
        """Test: PATCH /queue/tasks/{id}/toggle-schedulable updates flag."""
        payload = {"schedulable": False}
        response = client.patch(
            f"/queue/tasks/{sample_task.id}/toggle-schedulable",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["task"]["schedulable"] is False

    def test_update_task_parallelization(self, client: TestClient, db_session: Session, sample_task):
        """Test: PATCH /queue/tasks/{id}/parallelization updates flag."""
        payload = {"parallelization_allowed": False}
        response = client.patch(
            f"/queue/tasks/{sample_task.id}/parallelization",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["task"]["parallelization_allowed"] is False


class TestWorkPackageQueueEndpoints:
    """Tests for work package queue endpoints."""

    def test_update_work_package_queue_status(
        self, client: TestClient, db_session: Session, sample_work_package
    ):
        """Test: PATCH /queue/work-packages/{id}/queue-status updates status."""
        payload = {"queue_status": "in_progress"}
        response = client.patch(
            f"/queue/work-packages/{sample_work_package.id}/queue-status",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "WorkPackage queue_status updated"

    def test_enqueue_work_package(self, client: TestClient, db_session: Session, sample_work_package):
        """Test: POST /queue/enqueue-work-package/{id} creates task."""
        response = client.post(f"/queue/enqueue-work-package/{sample_work_package.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "task" in data
        assert "id" in data["task"]


class TestRequirementQueueEndpoints:
    """Tests for requirement queue endpoints."""

    def test_update_requirement_queue_status(
        self, client: TestClient, db_session: Session, sample_requirement
    ):
        """Test: PATCH /queue/requirements/{id}/queue-status updates status."""
        payload = {"queue_status": "in_progress"}
        response = client.patch(
            f"/queue/requirements/{sample_requirement.id}/queue-status",
            json=payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Requirement queue_status updated"


class TestQueueBlocking:
    """Tests for queue blocking functionality."""

    def test_queue_blocked_returns_true_when_blocking_task_exists(
        self, client: TestClient, db_session: Session
    ):
        """Test: Queue status shows blocked when blocking task exists."""
        # Create a blocking task
        blocking_task = Task(
            source_type="requirement",
            source_id=1,
            title="Blocking Task",
            prompt="Test",
            block_queue=True,
            status="queued",
            is_test=True,
        )
        db_session.add(blocking_task)
        db_session.commit()

        response = client.get("/queue/status")
        data = response.json()
        
        assert data["queue_blocked"] is True

    def test_queue_not_blocked_when_no_blocking_tasks(
        self, client: TestClient, db_session: Session
    ):
        """Test: Queue status shows not blocked when no blocking tasks."""
        # Create a non-blocking task
        normal_task = Task(
            source_type="requirement",
            source_id=1,
            title="Normal Task",
            prompt="Test",
            block_queue=False,
            status="queued",
            is_test=True,
        )
        db_session.add(normal_task)
        db_session.commit()

        response = client.get("/queue/status")
        data = response.json()
        
        assert data["queue_blocked"] is False
