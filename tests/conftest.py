import os
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Generator, Any
from unittest.mock import MagicMock
from sqlalchemy import text
import pytest
import requests
from dotenv import dotenv_values
from sqlmodel import SQLModel, Session, create_engine, select
from fastapi.testclient import TestClient

from execqueue.models.task import Task
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.dead_letter import DeadLetterQueue

# Importiere die Engine und Validierungsfunktionen
from execqueue.db.engine import (
    engine, 
    DATABASE_URL, 
    TEST_DATABASE_URL,
    _load_database_url,
    _load_test_database_url,
    _validate_connection,
    DOTENV_PATH
)
from execqueue.main import app

# Test-Setup: Prüfe ob .env existiert und valide ist
def _check_test_database_requirements():
    """Prüft ob alle Datenbank-Anforderungen für Tests erfüllt sind.
    
    Returns:
        tuple: (skip_reason: str | None, db_url: str)
               skip_reason ist None wenn alles ok, sonst Grund für Skip
    """
    # 1. Prüfe ob .env Datei existiert
    if not DOTENV_PATH.exists():
        return (
            f".env Datei nicht gefunden bei {DOTENV_PATH}. "
            "Tests werden übersprungen. Bitte .env Datei erstellen.",
            ""
        )
    
    # 2. Prüfe ob DATABASE_URL gesetzt ist
    try:
        database_url = _load_database_url()
    except (FileNotFoundError, ValueError) as e:
        return (str(e), "")
    
    # 3. Prüfe ob TEST_DATABASE_URL gesetzt ist (oder fallback zu DATABASE_URL)
    test_db_url = _load_test_database_url()
    if not test_db_url:
        test_db_url = database_url
    
    # 4. Prüfe Datenbankverbindung
    if not _validate_connection(test_db_url, "TEST_DATABASE"):
        return (
            f"Verbindung zu Test-Datenbank fehlgeschlagen. "
            "Bitte TEST_DATABASE_URL (oder DATABASE_URL) in .env prüfen. "
            "Tests werden übersprungen.",
            ""
        )
    
    return (None, test_db_url)


# Führe Prüfung durch und speichere Ergebnis
SKIP_REASON, VALID_DB_URL = _check_test_database_requirements()

# Setze TEST_DATABASE_URL für den Rest des Skripts
if VALID_DB_URL:
    os.environ["TEST_DATABASE_URL"] = VALID_DB_URL

TEST_QUEUE_PREFIX = os.getenv("TEST_QUEUE_PREFIX", "test_")
TEST_ID_START = 9000


# Custom pytest mark für Datenbank-Tests
def pytest_runtest_setup(item):
    """Skippt Tests wenn Datenbank-Anforderungen nicht erfüllt sind."""
    # Prüfe ob dieser Test eine Datenbank benötigt
    if item.get_closest_marker("db"):
        if SKIP_REASON:
            pytest.skip(SKIP_REASON)


@pytest.fixture
def client():
    """Create a test client for API client.
    
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
        queue_status="backlog",  # New field
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
        markdown_content="Sample requirement markdown content",  # Required field
        status="pending",
        queue_status="backlog",  # New field
        type="artifact",  # New field
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
        queue_status="backlog",  # New field
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
            queue_status="backlog",  # New field
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


# ============================================================================
# ACP Integration Test Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def acp_server() -> Generator[str, None, None]:
    """Start ACP server for integration tests and yield URL.
    
    Requires:
        - opencode CLI installed
        - OPENCODE_SERVER_PASSWORD set in environment
        - Port 8766 available
    """
    port = 8766
    url = f"http://127.0.0.1:{port}"
    
    # Check if ACP server should be started
    if not os.getenv("RUN_INTEGRATION_TESTS"):
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run ACP integration tests")
    
    # Start server
    password = os.getenv("OPENCODE_SERVER_PASSWORD", "test")
    proc = subprocess.Popen(
        ["opencode", "acp", "--port", str(port), "--hostname", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "OPENCODE_SERVER_PASSWORD": password}
    )
    
    # Wait for server to be ready
    max_wait = 15
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            response = requests.get(f"{url}/health", timeout=1)
            if response.status_code == 200:
                yield url
                break
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail(f"ACP server did not start within {max_wait}s")
    
    # Cleanup
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def test_project_dir(tmp_path) -> str:
    """Create a minimal test project directory with sample files."""
    # Create test Python file
    test_file = tmp_path / "test.py"
    test_file.write_text("# Test project\n\ndef hello():\n    return 'Hello World'\n")
    
    # Create README
    readme = tmp_path / "README.md"
    readme.write_text("# Test Project\n\nThis is a test project for ACP integration.\n")
    
    # Create requirements.txt (empty)
    (tmp_path / "requirements.txt").write_text("")
    
    return str(tmp_path)
