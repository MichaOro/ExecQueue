"""Tests for task API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from execqueue.api.dependencies import get_db_session
from execqueue.db.base import Base
from execqueue.db.session import build_session_factory
from execqueue.main import app


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
        "/api/tasks",
        json={
            "prompt": "Summarize the deployment checklist",
            "type": "task",
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
        "/api/tasks",
        json={
            "prompt": "First task",
            "type": "task",
            "created_by_type": "user",
            "created_by_ref": "telegram:1",
        },
    )
    second = task_api_client.post(
        "/api/tasks",
        json={
            "prompt": "Second task",
            "type": "requirement",
            "created_by_type": "agent",
            "created_by_ref": "agent:planner",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["task_number"] == 1
    assert second.json()["task_number"] == 2


def test_create_task_rejects_invalid_type(task_api_client):
    response = task_api_client.post(
        "/api/tasks",
        json={
            "prompt": "Should fail",
            "type": "incident",
            "created_by_type": "user",
            "created_by_ref": "telegram:123",
        },
    )

    assert response.status_code == 422


def test_get_task_status_returns_current_status(task_api_client):
    created = task_api_client.post(
        "/api/tasks",
        json={
            "prompt": "Check build logs",
            "type": "task",
            "created_by_type": "user",
            "created_by_ref": "telegram:456",
        },
    )

    response = task_api_client.get(
        f"/api/tasks/{created.json()['task_number']}/status"
    )

    assert response.status_code == 200
    assert response.json() == {
        "task_number": 1,
        "status": "backlog",
    }


def test_get_task_status_returns_404_for_unknown_task_number(task_api_client):
    response = task_api_client.get("/api/tasks/999/status")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task 999 not found."}
