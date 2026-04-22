import os
from pathlib import Path
from typing import Generator, Any
from unittest.mock import MagicMock

import pytest
from dotenv import dotenv_values
from sqlmodel import SQLModel, Session, create_engine

DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
DOTENV_VALUES = dotenv_values(DOTENV_PATH) if DOTENV_PATH.exists() else {}

TEST_DATABASE_URL = (
    os.getenv("TEST_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or DOTENV_VALUES.get("TEST_DATABASE_URL")
    or DOTENV_VALUES.get("DATABASE_URL")
)
TEST_QUEUE_PREFIX = (
    os.getenv("TEST_QUEUE_PREFIX")
    or DOTENV_VALUES.get("TEST_QUEUE_PREFIX")
    or "test_"
)
TEST_ID_START = 9000
SQLITE_FALLBACK_URL = "sqlite:///:memory:"
HAS_CONFIGURED_TEST_DB = bool(TEST_DATABASE_URL)
DB_REQUIRED_FIXTURES = {
    "db_session",
    "test_engine",
    "session_scope",
    "api_client",
    "e2e_client",
    "session_with_data",
    "sample_requirement",
    "sample_work_package",
    "sample_task",
    "sample_task_queue",
}

if TEST_DATABASE_URL:
    os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
    os.environ.setdefault("TEST_DATABASE_URL", TEST_DATABASE_URL)
else:
    # Keep imports working even when DB-backed tests are skipped.
    os.environ.setdefault("DATABASE_URL", SQLITE_FALLBACK_URL)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_db: test needs a configured external database connection",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if HAS_CONFIGURED_TEST_DB:
        return

    skip_marker = pytest.mark.skip(
        reason="requires configured TEST_DATABASE_URL or DATABASE_URL"
    )

    for item in items:
        if DB_REQUIRED_FIXTURES.intersection(item.fixturenames):
            item.add_marker(pytest.mark.requires_db)
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def test_engine() -> Any:
    """Create a test engine only when a real test DB is configured."""
    if not TEST_DATABASE_URL:
        pytest.skip("requires configured TEST_DATABASE_URL or DATABASE_URL")

    engine_kwargs: dict[str, Any] = {"echo": False}

    if "neon.tech" in TEST_DATABASE_URL:
        engine_kwargs["connect_args"] = {"sslmode": "require"}

    engine = create_engine(
        TEST_DATABASE_URL,
        **engine_kwargs,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(autouse=True)
def enable_test_queue_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EXECQUEUE_TEST_MODE", "true")
    monkeypatch.setenv("TEST_QUEUE_PREFIX", TEST_QUEUE_PREFIX)


@pytest.fixture
def db_session(test_engine: Any) -> Generator[Session, None, None]:
    """Function-scoped session with automatic rollback and cleanup after each test.
    
    Provides isolated tests - each test gets a clean state.
    Only deletes test data (is_test=True) to preserve production data.
    """
    from sqlmodel import delete
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    with Session(test_engine) as session:
        session.exec(delete(WorkPackage).where(WorkPackage.is_test == True))
        session.exec(delete(Task).where(Task.is_test == True))
        session.exec(delete(Requirement).where(Requirement.is_test == True))
        session.commit()
        
        yield session
        session.rollback()


@pytest.fixture
def session_scope(test_engine: Any) -> Generator[Session, None, None]:
    """Session-scoped transaction with rollback.
    
    Faster than function-scoped but less isolated.
    Use when tests within a file can share state.
    Only deletes test data (is_test=True) to preserve production data.
    """
    from sqlmodel import delete
    from execqueue.models.requirement import Requirement
    from execqueue.models.work_package import WorkPackage
    from execqueue.models.task import Task

    with Session(test_engine) as session:
        session.exec(delete(WorkPackage).where(WorkPackage.is_test == True))
        session.exec(delete(Task).where(Task.is_test == True))
        session.exec(delete(Requirement).where(Requirement.is_test == True))
        session.commit()
        
        yield session
        session.rollback()


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


@pytest.fixture
def sample_requirement(db_session: Session) -> Any:
    """Create a Requirement in the test database marked as test data."""
    from execqueue.models.requirement import Requirement

    requirement = Requirement(
        id=TEST_ID_START + 1,
        title=f"{TEST_QUEUE_PREFIX}Sample Requirement",
        description="This is a test requirement",
        markdown_content="# Sample Requirement\n\nTest content",
        verification_prompt=None,
        status="backlog",
        is_test=True,
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)
    return requirement


@pytest.fixture
def sample_work_package(db_session: Session, sample_requirement: Any) -> Any:
    """Create a WorkPackage linked to a requirement marked as test data."""
    from execqueue.models.work_package import WorkPackage

    work_package = WorkPackage(
        id=TEST_ID_START + 10,
        requirement_id=sample_requirement.id,
        title=f"{TEST_QUEUE_PREFIX}Sample Work Package",
        description="This is a test work package",
        status="backlog",
        execution_order=1,
        implementation_prompt="Implement this feature",
        verification_prompt="Verify the implementation",
        is_test=True,
    )
    db_session.add(work_package)
    db_session.commit()
    db_session.refresh(work_package)
    return work_package


@pytest.fixture
def sample_task(db_session: Session, sample_work_package: Any) -> Any:
    """Create a Task marked as test data."""
    from execqueue.models.task import Task

    task = Task(
        id=TEST_ID_START + 20,
        source_type="work_package",
        source_id=sample_work_package.id,
        title=f"{TEST_QUEUE_PREFIX}Sample Task",
        prompt="Implement the sample work package",
        verification_prompt="Verify the implementation",
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
def sample_task_queue(db_session: Session, sample_requirement: Any) -> list[Any]:
    """Create multiple Tasks marked as test data."""
    from execqueue.models.task import Task

    tasks = []
    for i, order in enumerate([3, 1, 2]):
        task = Task(
            id=TEST_ID_START + 30 + i,
            source_type="requirement",
            source_id=sample_requirement.id,
            title=f"{TEST_QUEUE_PREFIX}Task {i + 1}",
            prompt=f"Prompt for task {i + 1}",
            status="queued",
            execution_order=order,
            retry_count=0,
            max_retries=5,
            is_test=True,
        )
        db_session.add(task)
        tasks.append(task)

    db_session.commit()

    for task in tasks:
        db_session.refresh(task)

    return sorted(tasks, key=lambda t: t.execution_order)
