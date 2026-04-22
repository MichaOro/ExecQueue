import os
import pytest
from typing import Generator, Any
from unittest.mock import MagicMock, patch
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event

# Test database URL - uses SQLite file for persistence
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test.db")

# Test ID range - IDs >= 9000 are reserved for tests
TEST_ID_START = 9000


@pytest.fixture(scope="session")
def test_engine() -> Any:
    """Create a separate engine for tests using SQLite file."""
    engine = create_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    return engine


@pytest.fixture(scope="session", autouse=True)
def create_test_db_tables(test_engine: Any) -> None:
    """Create all database tables before test session starts."""
    SQLModel.metadata.create_all(test_engine)


@pytest.fixture
def db_session(test_engine: Any) -> Generator[Session, None, None]:
    """Function-scoped session with automatic rollback and cleanup after each test.
    
    Provides isolated tests - each test gets a clean state.
    All data is cleaned up after each test (table truncate).
    """
    from sqlmodel import delete
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    # Clean all tables before test
    with Session(test_engine) as cleanup_session:
        cleanup_session.exec(delete(WorkPackage))
        cleanup_session.exec(delete(Task))
        cleanup_session.exec(delete(Requirement))
        cleanup_session.commit()

    with Session(test_engine) as session:
        yield session
        session.rollback()


@pytest.fixture
def session_scope(test_engine: Any) -> Generator[Session, None, None]:
    """Session-scoped transaction with rollback.
    
    Faster than function-scoped but less isolated.
    Use when tests within a file can share state.
    """
    from sqlmodel import delete
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    # Clean all tables before test
    with Session(test_engine) as cleanup_session:
        cleanup_session.exec(delete(WorkPackage))
        cleanup_session.exec(delete(Task))
        cleanup_session.exec(delete(Requirement))
        cleanup_session.commit()

    with Session(test_engine) as session:
        yield session
        session.rollback()

        yield

        # Optional: Clean up after test as well
        session.exec(delete(WorkPackage).where(WorkPackage.id >= TEST_ID_START))
        session.exec(delete(Task).where(Task.id >= TEST_ID_START))
        session.exec(delete(Requirement).where(Requirement.id >= TEST_ID_START))
        session.commit()


@pytest.fixture(scope="session")
def test_engine_in_memory() -> Any:
    """Create an in-memory SQLite engine for isolated tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=True,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(test_engine: Any) -> Generator[Session, None, None]:
    """Function-scoped session with automatic rollback and cleanup after each test.
    
    Provides isolated tests - each test gets a clean state.
    All data is cleaned up after each test (table truncate).
    """
    from sqlmodel import select, delete
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    # Clean all tables before test
    with Session(test_engine) as cleanup_session:
        cleanup_session.exec(delete(WorkPackage))
        cleanup_session.exec(delete(Task))
        cleanup_session.exec(delete(Requirement))
        cleanup_session.commit()

    with Session(test_engine) as session:
        yield session
        session.rollback()


@pytest.fixture
def session_scope(test_engine: Any) -> Generator[Session, None, None]:
    """Session-scoped transaction with rollback.
    
    Faster than function-scoped but less isolated.
    Use when tests within a file can share state.
    """
    from sqlmodel import delete
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    # Clean all tables before test
    with Session(test_engine) as cleanup_session:
        cleanup_session.exec(delete(WorkPackage))
        cleanup_session.exec(delete(Task))
        cleanup_session.exec(delete(Requirement))
        cleanup_session.commit()

    with Session(test_engine) as session:
        yield session
        session.rollback()


# ============================================================================
# OpenCode Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_opencode_success() -> MagicMock:
    """Mock that always returns success ('done')."""
    mock = MagicMock()
    mock.return_value = "done"
    return mock


@pytest.fixture
def mock_opencode_failure() -> MagicMock:
    """Mock that always returns failure ('not_done')."""
    mock = MagicMock()
    mock.return_value = "not_done"
    return mock


@pytest.fixture
def mock_opencode_flaky() -> MagicMock:
    """Mock that alternates between success and failure.
    
    Useful for testing retry logic.
    """
    call_count = [0]
    
    def flaky_response(*args: Any, **kwargs: Any) -> str:
        call_count[0] += 1
        return "done" if call_count[0] % 2 == 0 else "not_done"
    
    mock = MagicMock(side_effect=flaky_response)
    return mock


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_requirement(db_session: Session) -> Any:
    """Create a sample Requirement in the test database with test ID range."""
    from execqueue.models.requirement import Requirement

    requirement = Requirement(
        id=TEST_ID_START + 1,
        title="Sample Requirement",
        description="This is a test requirement",
        markdown_content="# Sample Requirement\n\nTest content",
        verification_prompt=None,
        status="backlog",
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)
    return requirement


@pytest.fixture
def sample_work_package(db_session: Session, sample_requirement: Any) -> Any:
    """Create a sample WorkPackage linked to a requirement with test ID range."""
    from execqueue.models.work_package import WorkPackage

    work_package = WorkPackage(
        id=TEST_ID_START + 10,
        requirement_id=sample_requirement.id,
        title="Sample Work Package",
        description="This is a test work package",
        status="backlog",
        execution_order=1,
        implementation_prompt="Implement this feature",
        verification_prompt="Verify the implementation",
    )
    db_session.add(work_package)
    db_session.commit()
    db_session.refresh(work_package)
    return work_package


@pytest.fixture
def sample_task(db_session: Session, sample_work_package: Any) -> Any:
    """Create a sample Task with all relevant fields and test ID range."""
    from execqueue.models.task import Task

    task = Task(
        id=TEST_ID_START + 20,
        source_type="work_package",
        source_id=sample_work_package.id,
        title="Sample Task",
        prompt="Implement the sample work package",
        verification_prompt="Verify the implementation",
        status="queued",
        execution_order=1,
        retry_count=0,
        max_retries=5,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def sample_task_queue(db_session: Session, sample_requirement: Any) -> list[Any]:
    """Create multiple Tasks with different execution_order values and test ID range.
    
    Returns a list of created tasks sorted by execution_order.
    """
    from execqueue.models.task import Task

    tasks = []
    for i, order in enumerate([3, 1, 2]):
        task = Task(
            id=TEST_ID_START + 30 + i,
            source_type="requirement",
            source_id=sample_requirement.id,
            title=f"Task {i + 1}",
            prompt=f"Prompt for task {i + 1}",
            status="queued",
            execution_order=order,
            retry_count=0,
            max_retries=5,
        )
        db_session.add(task)
        tasks.append(task)

    db_session.commit()

    for task in tasks:
        db_session.refresh(task)

    return sorted(tasks, key=lambda t: t.execution_order)
