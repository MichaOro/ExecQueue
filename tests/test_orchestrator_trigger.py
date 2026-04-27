"""Tests for orchestrator trigger functionality."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from execqueue.db.base import Base
from execqueue.db.models import Task
from execqueue.orchestrator_trigger import trigger_orchestrator


@pytest.fixture
def trigger_session():
    """Provide an in-memory SQLite session for trigger tests."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = engine.connect()
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=session)
    db_session = SessionLocal()

    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


def test_trigger_orchestrator_returns_true_on_success(trigger_session):
    """Test that trigger returns True on successful execution."""
    task = Task(
        task_number=1,
        prompt="Test prompt",
        type="planning",
        max_retries=3,
        created_by_type="user",
        created_by_ref="test:123",
    )
    trigger_session.add(task)
    trigger_session.commit()
    trigger_session.refresh(task)

    result = trigger_orchestrator(trigger_session, task)

    assert result is True


def test_trigger_orchestrator_returns_false_on_exception(trigger_session):
    """Test that trigger returns False and logs warning on exception."""
    task = Task(
        task_number=1,
        prompt="Test prompt",
        type="execution",
        max_retries=3,
        created_by_type="user",
        created_by_ref="test:456",
    )
    trigger_session.add(task)
    trigger_session.commit()
    trigger_session.refresh(task)

    # Mock the logger to simulate an exception
    with patch("execqueue.orchestrator_trigger.logger") as mock_logger:
        mock_logger.info.side_effect = Exception("Simulated trigger failure")

        result = trigger_orchestrator(trigger_session, task)

        assert result is False
        mock_logger.warning.assert_called_once()
        assert "Orchestrator trigger failed" in str(mock_logger.warning.call_args)


def test_trigger_orchestrator_logs_info_on_success(trigger_session):
    """Test that trigger logs info message on success."""
    task = Task(
        task_number=42,
        prompt="Test prompt",
        type="analysis",
        max_retries=3,
        created_by_type="user",
        created_by_ref="test:789",
    )
    trigger_session.add(task)
    trigger_session.commit()
    trigger_session.refresh(task)

    with patch("execqueue.orchestrator_trigger.logger") as mock_logger:
        result = trigger_orchestrator(trigger_session, task)

        assert result is True
        mock_logger.info.assert_called_once()
        # Check the format string and arguments
        call_args = mock_logger.info.call_args
        assert "task" in str(call_args)
        assert "42" in str(call_args)


def test_trigger_orchestrator_works_for_all_task_types(trigger_session):
    """Test that trigger works for planning, execution, and analysis types."""
    for i, task_type in enumerate(["planning", "execution", "analysis"], start=1):
        task = Task(
            task_number=i,
            prompt=f"Test {task_type}",
            type=task_type,
            max_retries=3,
            created_by_type="user",
            created_by_ref="test:123",
        )
        trigger_session.add(task)
        trigger_session.commit()
        trigger_session.refresh(task)

        with patch("execqueue.orchestrator_trigger.logger") as mock_logger:
            result = trigger_orchestrator(trigger_session, task)

            assert result is True
            # Check that the task type is in the call arguments
            call_args = str(mock_logger.info.call_args)
            assert task_type in call_args

        # Clear session for next iteration
        trigger_session.rollback()
