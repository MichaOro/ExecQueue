from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task
from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.orchestrator.workflow_models import WorkflowContext, WorkflowStatus, Workflow
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


class TestWorkflowRepository:
    def test_create_workflow_persists_metadata(self, db_session):
        repo = WorkflowRepository()
        ctx = WorkflowContext(
            workflow_id=uuid4(),
            epic_id=None,
            requirement_id=uuid4(),
            tasks=[],
            dependencies={},
        )

        workflow = repo.create_workflow(db_session, ctx)

        assert workflow.id is not None
        assert workflow.id != ctx.workflow_id
        assert workflow.requirement_id == ctx.requirement_id
        assert workflow.status == WorkflowStatus.RUNNING.value

    def test_get_workflow_task_summary_aggregates_execution_statuses(self, db_session):
        repo = WorkflowRepository()
        workflow_id = uuid4()

        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.RUNNING.value))
        db_session.add_all(
            [
                TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.DONE.value),
                TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.DONE.value),
                TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.FAILED.value),
            ]
        )
        db_session.commit()

        summary = repo.get_workflow_task_summary(db_session, workflow_id)

        assert summary == {"done": 2, "failed": 1}

    def test_calculate_workflow_status_prefers_failed(self):
        repo = WorkflowRepository()

        assert repo.calculate_workflow_status({"done": 2, "failed": 1}) == WorkflowStatus.FAILED
        assert repo.calculate_workflow_status({"done": 3}) == WorkflowStatus.DONE
        assert repo.calculate_workflow_status({"done": 1, "queued": 1}) == WorkflowStatus.RUNNING
        assert repo.calculate_workflow_status({}) == WorkflowStatus.RUNNING

    def test_check_and_update_workflow_status_is_idempotent(self, db_session):
        repo = WorkflowRepository()
        workflow_id = uuid4()
        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.RUNNING.value))
        db_session.add_all(
            [
                TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.DONE.value),
                TaskExecution(id=uuid4(), task_id=uuid4(), workflow_id=workflow_id, status=ExecutionStatus.DONE.value),
            ]
        )
        db_session.commit()

        updated_first = repo.check_and_update_workflow_status(db_session, workflow_id)
        db_session.refresh(db_session.get(Workflow, workflow_id))
        updated_second = repo.check_and_update_workflow_status(db_session, workflow_id)

        assert updated_first is True
        assert db_session.get(Workflow, workflow_id).status == WorkflowStatus.DONE.value
        assert updated_second is False

    def test_set_runner_uuid_updates_existing_workflow(self, db_session):
        repo = WorkflowRepository()
        workflow_id = uuid4()
        db_session.add(Workflow(id=workflow_id, status=WorkflowStatus.RUNNING.value))
        db_session.commit()

        repo.set_runner_uuid(db_session, workflow_id, "runner-123")

        assert db_session.get(Workflow, workflow_id).runner_uuid == "runner-123"
