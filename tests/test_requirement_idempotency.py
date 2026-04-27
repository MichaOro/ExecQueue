"""Tests for requirement model and task idempotency."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from uuid import uuid4

from execqueue.db.base import Base
from execqueue.db.engine import build_engine
from execqueue.db.models import Requirement, Task, RequirementStatus
from execqueue.db.session import build_session_factory
from execqueue.settings import RuntimeEnvironment, Settings
from execqueue.tasks.service import (
    create_task,
    create_requirement,
    IdempotencyError,
)


class RuntimeTestSettings(Settings):
    """Settings variant that ignores the local .env file during tests."""

    model_config = Settings.model_config.copy()
    model_config["env_file"] = ""
    model_config["extra"] = "ignore"


def create_sqlite_session():
    """Create an in-memory SQLite session for testing."""
    settings = RuntimeTestSettings(
        app_env=RuntimeEnvironment.TEST,
        database_url_test="sqlite+pysqlite:///:memory:",
    )
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session = build_session_factory(engine)()
    return engine, session


class TestRequirementModel:
    """Tests for the Requirement model."""

    def test_requirement_defaults_are_applied(self):
        """Test that requirement defaults are correctly applied."""
        engine, session = create_sqlite_session()
        try:
            req = Requirement(
                title="Test Requirement",
                description="This is a test requirement",
            )
            session.add(req)
            session.commit()
            session.refresh(req)

            assert req.title == "Test Requirement"
            assert req.description == "This is a test requirement"
            assert req.status == RequirementStatus.DRAFT.value
            assert req.project_id is None
            assert req.id is not None
        finally:
            session.close()
            engine.dispose()

    def test_requirement_status_constraint(self):
        """Test that invalid requirement status is rejected."""
        engine, session = create_sqlite_session()
        try:
            req = Requirement(
                title="Test Requirement",
                description="This should fail",
                status="invalid_status",
            )
            session.add(req)

            with pytest.raises(IntegrityError):
                session.commit()
        finally:
            session.close()
            engine.dispose()

    def test_requirement_with_project(self):
        """Test requirement with project association."""
        engine, session = create_sqlite_session()
        try:
            # Create a project first
            from execqueue.db.models import Project

            project = Project(
                key="TEST",
                name="Test Project",
            )
            session.add(project)
            session.commit()
            session.refresh(project)

            # Create requirement with project
            req = Requirement(
                title="Test Requirement",
                description="Linked to project",
                project_id=project.id,
            )
            session.add(req)
            session.commit()
            session.refresh(req)

            assert req.project_id == project.id
        finally:
            session.close()
            engine.dispose()


class TestTaskIdempotency:
    """Tests for task idempotency key functionality."""

    def test_task_without_idempotency_key(self):
        """Test that tasks can be created without idempotency key."""
        engine, session = create_sqlite_session()
        try:
            task = create_task(
                session=session,
                prompt="Test prompt",
                task_type="planning",
                created_by_type="user",
                created_by_ref="test:123",
            )
            assert task.idempotency_key is None
        finally:
            session.close()
            engine.dispose()

    def test_task_with_idempotency_key(self):
        """Test that tasks can be created with idempotency key."""
        engine, session = create_sqlite_session()
        try:
            task = create_task(
                session=session,
                prompt="Test prompt",
                task_type="planning",
                created_by_type="user",
                created_by_ref="test:123",
                idempotency_key="unique-key-123",
            )
            assert task.idempotency_key == "unique-key-123"
        finally:
            session.close()
            engine.dispose()

    def test_duplicate_idempotency_key_raises_error(self):
        """Test that duplicate idempotency keys raise IdempotencyError."""
        engine, session = create_sqlite_session()
        try:
            # First task with idempotency key
            create_task(
                session=session,
                prompt="First task",
                task_type="planning",
                created_by_type="user",
                created_by_ref="test:123",
                idempotency_key="unique-key-123",
            )

            # Second task with same idempotency key should fail
            with pytest.raises(IdempotencyError) as exc_info:
                create_task(
                    session=session,
                    prompt="Second task",
                    task_type="execution",
                    created_by_type="user",
                    created_by_ref="test:456",
                    idempotency_key="unique-key-123",
                )

            assert exc_info.value.idempotency_key == "unique-key-123"
        finally:
            session.close()
            engine.dispose()

    def test_different_idempotency_keys_allowed(self):
        """Test that different idempotency keys are allowed."""
        engine, session = create_sqlite_session()
        try:
            task1 = create_task(
                session=session,
                prompt="First task",
                task_type="planning",
                created_by_type="user",
                created_by_ref="test:123",
                idempotency_key="key-1",
            )
            task2 = create_task(
                session=session,
                prompt="Second task",
                task_type="execution",
                created_by_type="user",
                created_by_ref="test:456",
                idempotency_key="key-2",
            )

            assert task1.idempotency_key == "key-1"
            assert task2.idempotency_key == "key-2"
        finally:
            session.close()
            engine.dispose()


class TestTaskRequirementLink:
    """Tests for task-to-requirement linking."""

    def test_task_without_requirement(self):
        """Test that tasks can be created without requirement link."""
        engine, session = create_sqlite_session()
        try:
            task = create_task(
                session=session,
                prompt="Standalone task",
                task_type="planning",
                created_by_type="user",
                created_by_ref="test:123",
            )
            assert task.requirement_id is None
        finally:
            session.close()
            engine.dispose()

    def test_task_with_requirement_link(self):
        """Test that tasks can be linked to requirements."""
        engine, session = create_sqlite_session()
        try:
            # Create requirement first
            req = create_requirement(
                session=session,
                title="Test Requirement",
                description="This is a test requirement",
            )

            # Create task linked to requirement
            task = create_task(
                session=session,
                prompt="Task for requirement",
                task_type="planning",
                created_by_type="user",
                created_by_ref="test:123",
                requirement_id=req.id,
            )

            assert task.requirement_id == req.id
        finally:
            session.close()
            engine.dispose()

    def test_task_with_invalid_requirement_id(self):
        """Test that invalid requirement_id is handled.

        Note: SQLite does not enforce foreign key constraints by default.
        This test verifies the task is created but the FK constraint
        would be enforced by PostgreSQL in production.
        """
        engine, session = create_sqlite_session()
        try:
            # SQLite doesn't enforce FK by default, so the task will be created
            # In PostgreSQL, this would raise IntegrityError
            task = create_task(
                session=session,
                prompt="Task with invalid requirement",
                task_type="planning",
                created_by_type="user",
                created_by_ref="test:123",
                requirement_id=uuid4(),  # Non-existent UUID
            )
            # Task is created but FK constraint would fail in PostgreSQL
            assert task.requirement_id is not None
        finally:
            session.close()
            engine.dispose()


class TestCreateRequirementService:
    """Tests for the create_requirement service function."""

    def test_create_requirement_draft(self):
        """Test creating a requirement with default draft status."""
        engine, session = create_sqlite_session()
        try:
            req = create_requirement(
                session=session,
                title="Test",
                description="Description",
            )
            assert req.status == "draft"
        finally:
            session.close()
            engine.dispose()

    def test_create_requirement_with_status(self):
        """Test creating a requirement with explicit status."""
        engine, session = create_sqlite_session()
        try:
            req = create_requirement(
                session=session,
                title="Test",
                description="Description",
                status="approved",
            )
            assert req.status == "approved"
        finally:
            session.close()
            engine.dispose()

    def test_create_requirement_invalid_status(self):
        """Test that invalid status raises ValueError."""
        engine, session = create_sqlite_session()
        try:
            with pytest.raises(ValueError) as exc_info:
                create_requirement(
                    session=session,
                    title="Test",
                    description="Description",
                    status="invalid",
                )
            assert "Invalid requirement status" in str(exc_info.value)
        finally:
            session.close()
            engine.dispose()

    def test_create_requirement_empty_title(self):
        """Test that empty title raises ValueError."""
        engine, session = create_sqlite_session()
        try:
            with pytest.raises(ValueError) as exc_info:
                create_requirement(
                    session=session,
                    title="",
                    description="Description",
                )
            assert "title must not be empty" in str(exc_info.value)
        finally:
            session.close()
            engine.dispose()

    def test_create_requirement_whitespace_title(self):
        """Test that whitespace-only title raises ValueError."""
        engine, session = create_sqlite_session()
        try:
            with pytest.raises(ValueError) as exc_info:
                create_requirement(
                    session=session,
                    title="   ",
                    description="Description",
                )
            assert "title must not be empty" in str(exc_info.value)
        finally:
            session.close()
            engine.dispose()

    def test_create_requirement_empty_description(self):
        """Test that empty description raises ValueError."""
        engine, session = create_sqlite_session()
        try:
            with pytest.raises(ValueError) as exc_info:
                create_requirement(
                    session=session,
                    title="Test",
                    description="",
                )
            assert "description must not be empty" in str(exc_info.value)
        finally:
            session.close()
            engine.dispose()

    def test_create_requirement_title_length_exceeded(self):
        """Test that title exceeding 255 chars raises ValueError."""
        engine, session = create_sqlite_session()
        try:
            with pytest.raises(ValueError) as exc_info:
                create_requirement(
                    session=session,
                    title="x" * 256,
                    description="Description",
                )
            assert "must not exceed 255 characters" in str(exc_info.value)
        finally:
            session.close()
            engine.dispose()

    def test_create_requirement_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        engine, session = create_sqlite_session()
        try:
            req = create_requirement(
                session=session,
                title="  Test Title  ",
                description="  Description  ",
            )
            assert req.title == "Test Title"
            assert req.description == "Description"
        finally:
            session.close()
            engine.dispose()
