import os
import time
from pathlib import Path
from typing import Generator, Any
from unittest.mock import MagicMock
from sqlalchemy import text

import pytest
from dotenv import dotenv_values
from sqlmodel import SQLModel, Session, create_engine, select
from fastapi.testclient import TestClient

from execqueue.models.task import Task
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.dead_letter import DeadLetterQueue
from execqueue.db.engine import engine
from execqueue.main import app

DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
DOTENV_VALUES = dotenv_values(DOTENV_PATH) if DOTENV_PATH.exists() else {}

TEST_DATABASE_URL = (
    os.getenv("TEST_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or DOTENV_VALUES.get("TEST_DATABASE_URL")
    or DOTENV_VALUES.get("DATABASE_URL")
)

TEST_QUEUE_PREFIX = os.getenv("TEST_QUEUE_PREFIX", "test_")
TEST_ID_START = 9000


@pytest.fixture
def client():
    """Create a test client for API tests.
    
    Overrides the get_session dependency to use the test database session.
    """
    from execqueue.db.session import get_session
    
    # Save existing overrides
    existing_overrides = app.dependency_overrides.copy()
    
    def override_get_session():
        """Override get_session for testing with a new session each time."""
        with Session(engine) as session:
            yield session
    
    # Set the override
    app.dependency_overrides[get_session] = override_get_session
    
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client
    
    # Restore previous overrides
    app.dependency_overrides.clear()
    app.dependency_overrides.update(existing_overrides)


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set up test environment."""
    monkeypatch.setenv("EXECQUEUE_TEST_MODE", "true")
    monkeypatch.setenv("TEST_QUEUE_PREFIX", "test_")
    yield


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    with Session(engine) as session:
        yield session


@pytest.fixture
def sample_task(db_session):
    """Create a sample task for testing.
    
    Uses dynamic ID allocation to avoid conflicts with existing test data.
    """
    # Get the next available ID by finding the max existing test ID
    from sqlalchemy import func
    max_id_result = db_session.exec(
        text("SELECT COALESCE(MAX(id), 8999) FROM tasks WHERE id >= 9000")
    ).one()
    # Handle different return types from SQLModel/SQLAlchemy
    if hasattr(max_id_result, '__getitem__'):
        max_id = max_id_result[0]
    elif hasattr(max_id_result, '_mapping'):
        max_id = list(max_id_result.values())[0]
    else:
        max_id = max_id_result
    next_id = int(max_id) + 1
    
    task = Task(
        id=next_id,
        source_type="requirement",
        source_id=next_id + 100,
        title=f"{TEST_QUEUE_PREFIX}Sample Task",
        prompt="Sample prompt for testing",
        verification_prompt="Verify this task",
        status="queued",
        execution_order=1,
        retry_count=0,
        max_retries=5,
        is_test=True,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def sample_requirement(db_session):
    """Create a sample requirement for testing."""
    req = Requirement(
        id=TEST_ID_START + 100,
        title=f"{TEST_QUEUE_PREFIX}Sample Requirement",
        description="Sample requirement description",
        status="pending",
        is_test=True,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


@pytest.fixture
def sample_work_package(db_session, sample_requirement):
    """Create a sample work package for testing."""
    wp = WorkPackage(
        id=TEST_ID_START + 200,
        requirement_id=sample_requirement.id,
        title=f"{TEST_QUEUE_PREFIX}Sample Work Package",
        description="Sample work package description",
        execution_order=1,
        status="pending",
        is_test=True,
    )
    db_session.add(wp)
    db_session.commit()
    db_session.refresh(wp)
    return wp


@pytest.fixture
def sample_task_queue(db_session, sample_requirement):
    """Create a queue of sample tasks for testing."""
    tasks = []
    for i in range(3):
        task = Task(
            id=TEST_ID_START + 30 + i,
            source_type="requirement",
            source_id=sample_requirement.id,
            title=f"{TEST_QUEUE_PREFIX}Task {i+1}",
            prompt=f"Prompt for task {i+1}",
            execution_order=i + 1,
            status="queued",
            is_test=True,
        )
        db_session.add(task)
        tasks.append(task)
    
    db_session.commit()
    for task in tasks:
        db_session.refresh(task)
    
    return tasks


@pytest.fixture
def dead_letter_entry(db_session, sample_task):
    """Create a sample dead letter queue entry."""
    from datetime import datetime, timezone
    
    dlq = DeadLetterQueue(
        task_id=sample_task.id,
        source_type=sample_task.source_type,
        source_id=sample_task.source_id,
        task_title=sample_task.title,
        task_prompt=sample_task.prompt,
        verification_prompt=sample_task.verification_prompt,
        final_status="max_retries_exceeded",
        failure_reason="Max retries exceeded",
        failure_details="Task validation failed after 5 retries",
        last_execution_output=sample_task.last_result,
        retry_count=5,
        max_retries=sample_task.max_retries,
        failed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(dlq)
    db_session.commit()
    db_session.refresh(dlq)
    return dlq


@pytest.fixture
def locked_task(db_session, sample_task):
    """Create a locked task for testing."""
    from datetime import datetime, timezone
    
    sample_task.locked_at = datetime.now(timezone.utc)
    sample_task.locked_by = "test-worker-1"
    db_session.add(sample_task)
    db_session.commit()
    db_session.refresh(sample_task)
    return sample_task


@pytest.fixture
def mock_worker_state(monkeypatch):
    """Mock worker state for health check tests."""
    from execqueue.api import health
    
    original_state = health._worker_state.copy()
    health._worker_state = {
        "started_at": time.time() - 3600,  # 1 hour ago
        "instance_id": "test-instance",
        "last_task_at": "2026-04-23T10:00:00Z",
        "is_running": True,
        "tasks_processed": 10,
        "tasks_failed": 1,
    }
    
    yield
    
    health._worker_state = original_state
