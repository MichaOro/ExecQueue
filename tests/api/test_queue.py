import pytest
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task


class TestQueueAPI:
    """API tests for queue endpoint."""

    def test_enqueue_requirement_with_work_packages(self, api_client, db_session):
        """Test: POST /queue/enqueue-requirement creates tasks for work packages."""
        from sqlmodel import select
        from execqueue.models.requirement import Requirement
        from execqueue.models.work_package import WorkPackage

        req = Requirement(
            id=9001,
            title="Test Req",
            description="Desc",
            markdown_content="Content",
            verification_prompt=None,
        )
        db_session.add(req)
        db_session.commit()
        db_session.refresh(req)

        wp1 = WorkPackage(
            id=9010,
            requirement_id=req.id,
            title="WP 1",
            description="Desc 1",
            execution_order=1,
        )
        wp2 = WorkPackage(
            id=9011,
            requirement_id=req.id,
            title="WP 2",
            description="Desc 2",
            execution_order=2,
        )
        db_session.add_all([wp1, wp2])
        db_session.commit()

        payload = {"requirement_id": req.id}

        response = api_client.post("/queue/enqueue-requirement", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Requirement enqueued"
        assert data["created_task_count"] == 2

        tasks = db_session.exec(select(Task).where(Task.source_id.in_([wp1.id, wp2.id]))).all()
        assert len(tasks) == 2

    def test_enqueue_requirement_without_work_packages(self, api_client, session_with_data):
        """Test: POST /queue/enqueue-requirement creates single task from requirement."""
        from sqlmodel import select
        req = Requirement(
            title="Standalone Requirement",
            description="No WPs",
            markdown_content="Content only",
        )
        session_with_data.add(req)
        session_with_data.commit()
        session_with_data.refresh(req)

        payload = {"requirement_id": req.id}

        response = api_client.post("/queue/enqueue-requirement", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Requirement enqueued"
        assert data["created_task_count"] == 1

        task = session_with_data.exec(
            select(Task).where(Task.source_id == req.id)
        ).first()
        assert task is not None
        assert task.source_type == "requirement"

    def test_enqueue_requirement_not_found(self, api_client):
        """Test: POST /queue/enqueue-requirement returns 404 for non-existent requirement."""
        payload = {"requirement_id": 9999}

        response = api_client.post("/queue/enqueue-requirement", json=payload)

        assert response.status_code == 404

    def test_enqueue_requirement_updates_requirement_status(self, api_client, session_with_data):
        """Test: Requirement status changes to planned after enqueue."""
        from sqlmodel import select
        req = Requirement(
            title="Status Test Req",
            description="Desc",
            markdown_content="Content",
        )
        session_with_data.add(req)
        session_with_data.commit()
        session_with_data.refresh(req)

        assert req.status == "backlog"

        payload = {"requirement_id": req.id}

        api_client.post("/queue/enqueue-requirement", json=payload)

        refreshed_req = session_with_data.get(Requirement, req.id)
        assert refreshed_req.status == "planned"

    def test_enqueue_requirement_sets_task_status_queued(self, api_client, session_with_data):
        """Test: Created tasks have status='queued'."""
        from sqlmodel import select
        req = Requirement(
            title="Task Status Req",
            description="Desc",
            markdown_content="Content",
        )
        session_with_data.add(req)
        session_with_data.commit()
        session_with_data.refresh(req)

        payload = {"requirement_id": req.id}

        api_client.post("/queue/enqueue-requirement", json=payload)

        task = session_with_data.exec(
            select(Task).where(Task.source_id == req.id)
        ).first()
        assert task.status == "queued"
