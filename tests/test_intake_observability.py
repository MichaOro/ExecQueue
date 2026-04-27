"""Tests for intake observability and error handling (AP 5)."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from execqueue.api.dependencies import get_db_session
from execqueue.db.base import Base
from execqueue.db.session import build_session_factory
from execqueue.main import app


@pytest.fixture
def observability_client():
    """Provide a TestClient with observability logging enabled."""
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


def test_intake_accepts_valid_planning_task(observability_client):
    """Test that valid planning task intake succeeds."""
    response = observability_client.post(
        "/api/task",
        json={
            "prompt": "Test prompt",
            "type": "planning",
            "created_by_type": "user",
            "created_by_ref": "telegram:123",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["task_number"] == 1
    assert data["status"] == "backlog"


def test_intake_accepts_valid_requirement(observability_client):
    """Test that valid requirement intake succeeds."""
    response = observability_client.post(
        "/api/task",
        json={
            "prompt": "Requirement description",
            "type": "requirement",
            "created_by_type": "user",
            "created_by_ref": "telegram:456",
            "title": "Test Requirement",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["task_number"] == 1
    assert data["status"] == "backlog"


def test_intake_rejects_invalid_type(observability_client):
    """Test that invalid task type is rejected with 422."""
    response = observability_client.post(
        "/api/task",
        json={
            "prompt": "Test",
            "type": "invalid_type",
            "created_by_type": "user",
            "created_by_ref": "test:123",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["detail"]["errors"][0]["field"] == "type"


def test_intake_rejects_missing_title_for_requirement(observability_client):
    """Test that missing title for requirement type is rejected."""
    response = observability_client.post(
        "/api/task",
        json={
            "prompt": "Test",
            "type": "requirement",
            "created_by_type": "user",
            "created_by_ref": "test:123",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    data = response.json()
    assert "detail" in data
    assert "title" in str(data["detail"])


def test_intake_rejects_empty_prompt(observability_client):
    """Test that empty prompt is rejected."""
    response = observability_client.post(
        "/api/task",
        json={
            "prompt": "",
            "type": "planning",
            "created_by_type": "user",
            "created_by_ref": "test:123",
        },
    )

    assert response.status_code == 422


def test_intake_accepts_all_task_types(observability_client):
    """Test that all valid task types are accepted."""
    for task_type in ["planning", "execution", "analysis"]:
        response = observability_client.post(
            "/api/task",
            json={
                "prompt": f"Test {task_type}",
                "type": task_type,
                "created_by_type": "user",
                "created_by_ref": "test:123",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED, f"Failed for type: {task_type}"


def test_logger_is_configured_for_domain_module():
    """Test that the domain module has a properly configured logger."""
    import execqueue.api.routes.domain as domain_module

    logger = domain_module.logger
    assert logger is not None
    assert logger.name == "execqueue.api.routes.domain"
    assert logger.level == logging.NOTSET  # Uses root logger level


def test_error_handling_path_exists_for_idempotency(observability_client):
    """Test that duplicate idempotency keys return 409."""
    payload = {
        "prompt": "Test",
        "type": "planning",
        "created_by_type": "user",
        "created_by_ref": "test:123",
        "idempotency_key": "test-idempotency-key",
    }

    first_response = observability_client.post("/api/task", json=payload)
    second_response = observability_client.post("/api/task", json=payload)

    assert first_response.status_code == status.HTTP_201_CREATED
    assert second_response.status_code == status.HTTP_409_CONFLICT
    assert "Duplicate request" in second_response.json()["detail"]


def test_prompt_not_logged(observability_client, caplog):
    """Prompt content should never appear in intake or service logs."""
    secret_prompt = "SECRET_PROMPT_SHOULD_NOT_APPEAR_IN_LOGS"

    with caplog.at_level(logging.INFO):
        response = observability_client.post(
            "/api/task",
            json={
                "prompt": secret_prompt,
                "type": "planning",
                "created_by_type": "user",
                "created_by_ref": "telegram:123",
            },
        )

    assert response.status_code == status.HTTP_201_CREATED
    assert secret_prompt not in caplog.text
