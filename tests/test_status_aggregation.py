"""Tests for workflow status aggregation (REQ-017 P3)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task, TaskStatus
from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus
from execqueue.orchestrator.workflow_repo import WorkflowRepository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestWorkflowStatusAggregation:
    """Tests for WorkflowRepository status aggregation logic."""

    def test_failed_task_propagates_to_workflow(self, db_session):
        """Workflow becomes FAILED when any task execution is FAILED."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.RUNNING.value))
        db_session.add_all([
            TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.DONE.value),
            TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.FAILED.value),
        ])
        db_session.commit()

        updated = repo.check_and_update_workflow_status(db_session, workflow_id)
        db_session.refresh(db_session.get(Workflow, workflow_id))

        assert updated is True
        assert db_session.get(Workflow, workflow_id).status == WorkflowStatus.FAILED.value

    def test_all_completed_sets_workflow_done(self, db_session):
        """Workflow becomes DONE when all task executions are DONE."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.RUNNING.value))
        db_session.add_all([
            TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.DONE.value),
            TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.DONE.value),
        ])
        db_session.commit()

        updated = repo.check_and_update_workflow_status(db_session, workflow_id)
        assert updated is True
        assert db_session.get(Workflow, workflow_id).status == WorkflowStatus.DONE.value

    def test_mixed_status_keeps_running(self, db_session):
        """Workflow stays RUNNING when some tasks are still active."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.RUNNING.value))
        db_session.add_all([
            TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.DONE.value),
            TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.IN_PROGRESS.value),
        ])
        db_session.commit()

        updated = repo.check_and_update_workflow_status(db_session, workflow_id)
        assert updated is False
        assert db_session.get(Workflow, workflow_id).status == WorkflowStatus.RUNNING.value

    def test_no_executions_keeps_running(self, db_session):
        """Workflow with no task executions stays RUNNING."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.RUNNING.value))
        db_session.commit()

        updated = repo.check_and_update_workflow_status(db_session, workflow_id)
        assert updated is False
        assert db_session.get(Workflow, workflow_id).status == WorkflowStatus.RUNNING.value

    def test_already_done_workflow_is_not_updated(self, db_session):
        """Workflow already in DONE or FAILED state is not re-aggregated."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.DONE.value))
        db_session.commit()

        updated = repo.check_and_update_workflow_status(db_session, workflow_id)
        assert updated is False

    def test_already_failed_workflow_is_not_updated(self, db_session):
        """Workflow already in FAILED state is not re-aggregated."""
        repo = WorkflowRepository()
        workflow_id = uuid4()
        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.FAILED.value))
        db_session.commit()

        updated = repo.check_and_update_workflow_status(db_session, workflow_id)
        assert updated is False

    def test_calculate_workflow_status_all_done(self):
        repo = WorkflowRepository()
        assert repo.calculate_workflow_status({"done": 3}) == WorkflowStatus.DONE

    def test_calculate_workflow_status_any_failed(self):
        repo = WorkflowRepository()
        assert repo.calculate_workflow_status({"done": 2, "failed": 1}) == WorkflowStatus.FAILED

    def test_calculate_workflow_status_mixed(self):
        repo = WorkflowRepository()
        assert repo.calculate_workflow_status({"done": 1, "queued": 1}) == WorkflowStatus.RUNNING

    def test_calculate_workflow_status_empty(self):
        repo = WorkflowRepository()
        assert repo.calculate_workflow_status({}) == WorkflowStatus.RUNNING
