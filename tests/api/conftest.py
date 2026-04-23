import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from execqueue.main import app
from execqueue.db.session import get_session


@pytest.fixture(scope="session")
def client() -> TestClient:
    """FastAPI TestClient for API tests."""
    return TestClient(app)


@pytest.fixture
def api_client(db_session: Session):
    """TestClient with custom session dependency overridden.
    
    Uses the same pattern as tests/conftest.py client fixture.
    """
    # Save existing overrides
    existing_overrides = app.dependency_overrides.copy()
    
    def override_get_session():
        """Override get_session for testing with a new session each time."""
        with Session(db_session.bind) as session:
            yield session
    
    # Set the override
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    # Restore previous overrides
    app.dependency_overrides.clear()
    app.dependency_overrides.update(existing_overrides)




@pytest.fixture
def session_with_data(db_session: Session):
    """Session with some pre-created test data."""
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    req = Requirement(
        id=None,
        title="test_Test Requirement",
        description="Test desc",
        markdown_content="Test content",
        verification_prompt=None,
        is_test=True,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    wp = WorkPackage(
        id=None,
        requirement_id=req.id,
        title="test_Test WP",
        description="Test WP desc",
        execution_order=1,
        is_test=True,
    )
    db_session.add(wp)
    db_session.commit()
    db_session.refresh(wp)

    task = Task(
        id=None,
        source_type="work_package",
        source_id=wp.id,
        title="test_Test Task",
        prompt="Test prompt",
        execution_order=1,
        status="backlog",
        is_test=True,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    return db_session
