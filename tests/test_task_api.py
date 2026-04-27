"""Tests for task API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from execqueue.api.dependencies import get_db_session
from execqueue.db.base import Base
from execqueue.db.session import build_session_factory
from execqueue.main import app
from execqueue.tasks.service import create_task


@pytest.fixture
def task_api_client():
    """Provide a TestClient backed by an isolated SQLite database."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    def override_get_db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_create_task_returns_public_task_number_and_backlog_status(task_api_client):
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Summarize the deployment checklist",
            "type": "planning",
            "created_by_type": "user",
            "created_by_ref": "telegram:123",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "task_number": 1,
        "status": "backlog",
    }


def test_create_task_assigns_unique_task_numbers(task_api_client):
    first = task_api_client.post(
        "/api/task",
        json={
            "prompt": "First task",
            "type": "planning",
            "created_by_type": "user",
            "created_by_ref": "telegram:1",
        },
    )
    second = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Second task",
            "type": "execution",
            "created_by_type": "agent",
            "created_by_ref": "agent:executor",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["task_number"] == 1
    assert second.json()["task_number"] == 2


def test_create_task_accepts_planning_type(task_api_client):
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Plan the deployment",
            "type": "planning",
            "created_by_type": "user",
            "created_by_ref": "telegram:123",
        },
    )

    assert response.status_code == 201
    assert response.json()["task_number"] == 1
    assert response.json()["status"] == "backlog"


def test_create_task_accepts_execution_type(task_api_client):
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Execute the deployment",
            "type": "execution",
            "created_by_type": "agent",
            "created_by_ref": "agent:executor",
        },
    )

    assert response.status_code == 201
    assert response.json()["task_number"] == 1
    assert response.json()["status"] == "backlog"


def test_create_task_accepts_analysis_type(task_api_client):
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Analyze the build logs",
            "type": "analysis",
            "created_by_type": "user",
            "created_by_ref": "telegram:456",
        },
    )

    assert response.status_code == 201
    assert response.json()["task_number"] == 1
    assert response.json()["status"] == "backlog"


def test_create_task_accepts_requirement_and_maps_to_planning(task_api_client):
    """Requirement type should be accepted and creates Requirement + Planning task.

    For requirement type, both a Requirement record and a Planning task are created.
    The title field is required for requirement type.
    """
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Implement user authentication",
            "type": "requirement",
            "created_by_type": "user",
            "created_by_ref": "telegram:789",
            "title": "User Authentication Feature",
        },
    )

    assert response.status_code == 201
    assert response.json()["task_number"] == 1
    assert response.json()["status"] == "backlog"


def test_create_task_rejects_invalid_type_with_structured_error(task_api_client):
    """Invalid type should return structured validation error."""
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Should fail",
            "type": "incident",
            "created_by_type": "user",
            "created_by_ref": "telegram:123",
        },
    )

    assert response.status_code == 422
    data = response.json()
    assert data["detail"]["detail"] == "Intake validation failed"
    assert data["detail"]["errors"] == [
        {
            "field": "type",
            "reason": "Invalid task type 'incident'. Allowed intake types: analysis, execution, planning, requirement",
            "expected": "analysis, execution, planning, requirement",
        }
    ]


def test_get_task_status_returns_current_status(task_api_client):
    created = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Check build logs",
            "type": "analysis",
            "created_by_type": "user",
            "created_by_ref": "telegram:456",
        },
    )

    response = task_api_client.get(
        f"/api/task/{created.json()['task_number']}/status"
    )

    assert response.status_code == 200
    assert response.json() == {
        "task_number": 1,
        "status": "backlog",
    }


def test_get_task_status_returns_404_for_unknown_task_number(task_api_client):
    response = task_api_client.get("/api/task/999/status")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task 999 not found."}


def test_create_task_rejects_empty_prompt(task_api_client):
    """Empty prompt should be rejected by Pydantic validation."""
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "",
            "type": "planning",
            "created_by_type": "user",
            "created_by_ref": "telegram:123",
        },
    )

    assert response.status_code == 422


def test_create_task_rejects_missing_created_by_ref(task_api_client):
    """Missing created_by_ref should be rejected."""
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Test task",
            "type": "planning",
            "created_by_type": "user",
            "created_by_ref": "",
        },
    )

    assert response.status_code == 422


def test_create_task_handles_duplicate_idempotency_key(task_api_client):
    """Duplicate idempotency key should return 409 Conflict."""
    payload = {
        "prompt": "Test task",
        "type": "planning",
        "created_by_type": "user",
        "created_by_ref": "telegram:123",
        "idempotency_key": "duplicate-key-123",
    }

    first_response = task_api_client.post("/api/task", json=payload)
    second_response = task_api_client.post("/api/task", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Duplicate request: task with idempotency_key 'duplicate-key-123' already exists."
    }


def test_create_requirement_handles_duplicate_idempotency_key(task_api_client):
    """Requirement intake should also return 409 for duplicate idempotency keys."""
    payload = {
        "prompt": "Implement user authentication",
        "type": "requirement",
        "created_by_type": "user",
        "created_by_ref": "telegram:789",
        "title": "User Authentication Feature",
        "idempotency_key": "duplicate-requirement-key-123",
    }

    first_response = task_api_client.post("/api/task", json=payload)
    second_response = task_api_client.post("/api/task", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Duplicate request: task with idempotency_key 'duplicate-requirement-key-123' already exists."
    }


def test_create_requirement_rejects_missing_title(task_api_client):
    """Requirement type without title should be rejected with structured error."""
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Implement user authentication",
            "type": "requirement",
            "created_by_type": "user",
            "created_by_ref": "telegram:789",
        },
    )

    assert response.status_code == 422
    data = response.json()
    assert data["detail"]["detail"] == "Intake validation failed"
    assert data["detail"]["errors"] == [
        {
            "field": "title",
            "reason": "Requirement title must not be empty",
            "expected": "non-empty string (max 255 chars)",
        }
    ]


def test_create_requirement_rejects_title_too_long(task_api_client):
    """Requirement type with an oversized title should be rejected."""
    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Implement user authentication",
            "type": "requirement",
            "created_by_type": "user",
            "created_by_ref": "telegram:789",
            "title": "x" * 256,
        },
    )

    assert response.status_code == 422


def test_create_requirement_creates_requirement_and_task(task_api_client):
    """Requirement intake should create both Requirement and Planning task."""
    from execqueue.db.models import Requirement

    response = task_api_client.post(
        "/api/task",
        json={
            "prompt": "Implement user authentication",
            "type": "requirement",
            "created_by_type": "user",
            "created_by_ref": "telegram:789",
            "title": "User Authentication Feature",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["task_number"] == 1
    assert data["status"] == "backlog"

    # Verify Requirement was created by querying the DB
    session = None
    try:
        override_func = task_api_client.app.dependency_overrides.get(get_db_session)
        if override_func:
            session_gen = override_func()
            session = next(session_gen)

            # Check that a requirement with the given title exists
            req = session.execute(
                select(Requirement).where(Requirement.title == "User Authentication Feature")
            ).scalar_one_or_none()
            assert req is not None
            assert req.description == "Implement user authentication"
            assert req.status == "draft"
    finally:
        if session:
            session.close()
