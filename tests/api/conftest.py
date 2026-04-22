import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from execqueue.main import app
from execqueue.db.engine import get_session


@pytest.fixture(scope="session")
def client() -> TestClient:
    """FastAPI TestClient for API tests."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """In-memory SQLite session for isolated API tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


@pytest.fixture
def api_client(db_session: Session):
    """TestClient with custom session dependency overridden."""
    def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def cleanup_before_test(db_session: Session):
    """Automatically clean database before each test."""
    from sqlmodel import delete
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    db_session.exec(delete(WorkPackage))
    db_session.exec(delete(Task))
    db_session.exec(delete(Requirement))
    db_session.commit()


@pytest.fixture
def session_with_data(db_session: Session):
    """Session with some pre-created test data."""
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    req = Requirement(
        id=9001,
        title="Test Requirement",
        description="Test desc",
        markdown_content="Test content",
        verification_prompt=None,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    wp = WorkPackage(
        id=9010,
        requirement_id=req.id,
        title="Test WP",
        description="Test WP desc",
        execution_order=1,
    )
    db_session.add(wp)
    db_session.commit()
    db_session.refresh(wp)

    task = Task(
        id=9020,
        source_type="work_package",
        source_id=wp.id,
        title="Test Task",
        prompt="Test prompt",
        execution_order=1,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    return db_session
