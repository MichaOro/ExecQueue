"""REQ-009 Flow validation tests (AP 6).

This module verifies the complete REQ-009 intake flow:
- All four input types (requirement, planning, execution, analysis)
- Correct mapping to task types
- Requirement creates both Requirement record and Planning task
- All successful intakes trigger the orchestrator exactly once
- Invalid artifacts produce no task and no trigger
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from execqueue.api.dependencies import get_db_session
from execqueue.db.base import Base
from execqueue.db.models import Requirement, Task
from execqueue.db.session import build_session_factory
from execqueue.main import app


@pytest.fixture
def flow_client():
    """Provide a TestClient with an isolated in-memory database."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    def get_session():
        return session_factory()

    def override_get_db_session():
        session = get_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        with TestClient(app) as client:
            yield client, get_session
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


class TestREQ009_InputTypes:
    """Test all four REQ-009 input types are accepted."""

    def test_accepts_planning_input_type(self, flow_client):
        """Planning input creates a planning task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Plan the deployment",
                "type": "planning",
                "created_by_type": "user",
                "created_by_ref": "test:1",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["status"] == "backlog"

    def test_accepts_execution_input_type(self, flow_client):
        """Execution input creates an execution task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Execute the deployment",
                "type": "execution",
                "created_by_type": "user",
                "created_by_ref": "test:2",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["status"] == "backlog"

    def test_accepts_analysis_input_type(self, flow_client):
        """Analysis input creates an analysis task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Analyze the build logs",
                "type": "analysis",
                "created_by_type": "user",
                "created_by_ref": "test:3",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["status"] == "backlog"

    def test_accepts_requirement_input_type(self, flow_client):
        """Requirement input creates a requirement and planning task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Implement user auth",
                "type": "requirement",
                "created_by_type": "user",
                "created_by_ref": "test:4",
                "title": "User Authentication",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["status"] == "backlog"


class TestREQ009_RequirementMapping:
    """Test requirement → requirement + planning task mapping."""

    def test_requirement_creates_requirement_record(self, flow_client):
        """Requirement intake creates exactly one Requirement record."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Test requirement",
                "type": "requirement",
                "created_by_type": "user",
                "created_by_ref": "test:1",
                "title": "Test Title",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Verify Requirement was created
        session = flow_client[1]()
        try:
            req = session.execute(
                select(Requirement).where(Requirement.title == "Test Title")
            ).scalar_one_or_none()
            assert req is not None
            assert req.description == "Test requirement"
            assert req.status == "draft"
        finally:
            session.close()

    def test_requirement_creates_planning_task(self, flow_client):
        """Requirement intake creates exactly one Planning task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Test requirement",
                "type": "requirement",
                "created_by_type": "user",
                "created_by_ref": "test:1",
                "title": "Test Title",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Verify Planning task was created
        session = flow_client[1]()
        try:
            task = session.execute(
                select(Task).where(Task.type == "planning")
            ).scalar_one_or_none()
            assert task is not None
            assert task.prompt == "Test requirement"
        finally:
            session.close()

    def test_requirement_links_task_to_requirement(self, flow_client):
        """Requirement intake links the task to the requirement."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Test requirement",
                "type": "requirement",
                "created_by_type": "user",
                "created_by_ref": "test:1",
                "title": "Test Title",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Verify task.requirement_id is set
        session = flow_client[1]()
        try:
            task = session.execute(select(Task)).scalar_one_or_none()
            req = session.execute(select(Requirement)).scalar_one_or_none()
            assert task is not None
            assert req is not None
            assert task.requirement_id == req.id
        finally:
            session.close()


class TestREQ009_DirectTaskCreation:
    """Test direct task creation for non-requirement types."""

    def test_planning_creates_only_task_no_requirement(self, flow_client):
        """Planning input creates only a task, no requirement."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Plan it",
                "type": "planning",
                "created_by_type": "user",
                "created_by_ref": "test:1",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        session = flow_client[1]()
        try:
            tasks = session.execute(select(Task)).scalars().all()
            requirements = session.execute(select(Requirement)).scalars().all()
            assert len(tasks) == 1
            assert len(requirements) == 0
        finally:
            session.close()

    def test_execution_creates_only_task(self, flow_client):
        """Execution input creates only an execution task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Execute it",
                "type": "execution",
                "created_by_type": "user",
                "created_by_ref": "test:1",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        session = flow_client[1]()
        try:
            task = session.execute(select(Task)).scalar_one_or_none()
            assert task is not None
            assert task.type == "execution"
        finally:
            session.close()

    def test_analysis_creates_only_task(self, flow_client):
        """Analysis input creates only an analysis task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Analyze it",
                "type": "analysis",
                "created_by_type": "user",
                "created_by_ref": "test:1",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        session = flow_client[1]()
        try:
            task = session.execute(select(Task)).scalar_one_or_none()
            assert task is not None
            assert task.type == "analysis"
        finally:
            session.close()


class TestREQ009_OrchestratorTrigger:
    """Test orchestrator trigger behavior."""

    def test_trigger_called_once_for_planning(self, flow_client):
        """Planning intake triggers orchestrator exactly once."""
        client, get_session = flow_client
        with patch("execqueue.tasks.service.trigger_orchestrator") as mock_trigger:
            response = client.post(
                "/api/task",
                json={
                    "prompt": "Test",
                    "type": "planning",
                    "created_by_type": "user",
                    "created_by_ref": "test:1",
                },
            )

            assert response.status_code == status.HTTP_201_CREATED
            mock_trigger.assert_called_once()

    def test_trigger_called_once_for_requirement(self, flow_client):
        """Requirement intake triggers orchestrator exactly once."""
        client, get_session = flow_client
        with patch("execqueue.tasks.service.trigger_orchestrator") as mock_trigger:
            response = client.post(
                "/api/task",
                json={
                    "prompt": "Test",
                    "type": "requirement",
                    "created_by_type": "user",
                    "created_by_ref": "test:1",
                    "title": "Test",
                },
            )

            assert response.status_code == status.HTTP_201_CREATED
            mock_trigger.assert_called_once()

    def test_trigger_called_for_all_task_types(self, flow_client):
        """All task types trigger orchestrator exactly once."""
        client, get_session = flow_client
        for task_type in ["planning", "execution", "analysis"]:
            with patch("execqueue.tasks.service.trigger_orchestrator") as mock_trigger:
                response = client.post(
                    "/api/task",
                    json={
                        "prompt": f"Test {task_type}",
                        "type": task_type,
                        "created_by_type": "user",
                        "created_by_ref": "test:1",
                    },
                )

                assert response.status_code == status.HTTP_201_CREATED
                mock_trigger.assert_called_once()

    def test_trigger_failure_still_creates_task(self, flow_client):
        """A reported trigger failure must not undo a successful task creation."""
        client, get_session = flow_client

        with patch(
            "execqueue.tasks.service.trigger_orchestrator",
            return_value=False,
        ) as mock_trigger:
            response = client.post(
                "/api/task",
                json={
                    "prompt": "Test",
                    "type": "planning",
                    "created_by_type": "user",
                    "created_by_ref": "test:1",
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        mock_trigger.assert_called_once()

        session = get_session()
        try:
            task = session.execute(select(Task)).scalar_one_or_none()
            assert task is not None
            assert task.type == "planning"
        finally:
            session.close()


class TestREQ009_NegativeTests:
    """Test that invalid artifacts are rejected without side effects."""

    def test_invalid_type_creates_no_task(self, flow_client):
        """Invalid type is rejected and creates no task."""
        initial_task_count = 0  # Empty DB

        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Test",
                "type": "invalid_type",
                "created_by_type": "user",
                "created_by_ref": "test:1",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        session = flow_client[1]()
        try:
            tasks = session.execute(select(Task)).scalars().all()
            assert len(tasks) == initial_task_count
        finally:
            session.close()

    def test_missing_prompt_creates_no_task(self, flow_client):
        """Empty prompt is rejected and creates no task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "",
                "type": "planning",
                "created_by_type": "user",
                "created_by_ref": "test:1",
            },
        )

        assert response.status_code == 422

        session = flow_client[1]()
        try:
            tasks = session.execute(select(Task)).scalars().all()
            assert len(tasks) == 0
        finally:
            session.close()

    def test_missing_title_for_requirement_creates_nothing(self, flow_client):
        """Missing title for requirement rejects and creates no requirement or task."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Test",
                "type": "requirement",
                "created_by_type": "user",
                "created_by_ref": "test:1",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        session = flow_client[1]()
        try:
            tasks = session.execute(select(Task)).scalars().all()
            requirements = session.execute(select(Requirement)).scalars().all()
            assert len(tasks) == 0
            assert len(requirements) == 0
        finally:
            session.close()

    def test_trigger_not_called_for_invalid_input(self, flow_client):
        """Invalid input does not trigger orchestrator."""
        with patch("execqueue.tasks.service.trigger_orchestrator") as mock_trigger:
            response = (flow_client[0]).post(
                "/api/task",
                json={
                    "prompt": "Test",
                    "type": "invalid_type",
                    "created_by_type": "user",
                    "created_by_ref": "test:1",
                },
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
            mock_trigger.assert_not_called()


class TestREQ009_TaskStatus:
    """Test that all created tasks have backlog status."""

    def test_planning_task_has_backlog_status(self, flow_client):
        """Planning task is created with backlog status."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Test",
                "type": "planning",
                "created_by_type": "user",
                "created_by_ref": "test:1",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["status"] == "backlog"

    def test_requirement_task_has_backlog_status(self, flow_client):
        """Requirement-created planning task has backlog status."""
        response = (flow_client[0]).post(
            "/api/task",
            json={
                "prompt": "Test",
                "type": "requirement",
                "created_by_type": "user",
                "created_by_ref": "test:1",
                "title": "Test",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["status"] == "backlog"
