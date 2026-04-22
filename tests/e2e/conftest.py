import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from execqueue.main import app
from execqueue.db.engine import get_session


@pytest.fixture
def e2e_client():
    """E2E TestClient with fresh in-memory database per test.
    
    Function scope ensures each test gets a completely fresh database.
    Uses StaticPool to share in-memory DB with FastAPI dependency overrides.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
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
