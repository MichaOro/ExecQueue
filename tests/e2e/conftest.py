import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from execqueue.main import app
from execqueue.db.engine import get_session


@pytest.fixture
def e2e_client(test_engine, db_session):
    """E2E TestClient backed by the configured test database."""
    def override_get_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    app.dependency_overrides.clear()


def mock_opencode_done():
    """Helper to create a mock that returns 'done'."""
    return type(
        "MockResult",
        (),
        {
            "status": "completed",
            "raw_output": '{"status": "done", "summary": "Completed successfully."}',
            "summary": "Completed successfully.",
        },
    )()


def mock_opencode_not_done():
    """Helper to create a mock that returns 'not_done'."""
    return type(
        "MockResult",
        (),
        {
            "status": "completed",
            "raw_output": '{"status": "not_done", "summary": "Failed to complete."}',
            "summary": "Failed to complete.",
        },
    )()
