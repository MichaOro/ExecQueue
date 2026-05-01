from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task, TaskStatus
from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.orchestrator.idempotency_service import IdempotencyContext
from execqueue.orchestrator.main import Orchestrator
from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus


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


def create_task(session, workflow_id=None, **overrides) -> Task:
    task = Task(
        task_number=overrides.pop("task_number", 1),
        title=overrides.pop("title", "Task"),
        prompt=overrides.pop("prompt", "Prompt"),
        type=overrides.pop("type", "execution"),
        status=overrides.pop("status", TaskStatus.BACKLOG.value),
        max_retries=overrides.pop("max_retries", 3),
        created_by_type=overrides.pop("created_by_type", "agent"),
        created_by_ref=overrides.pop("created_by_ref", "test"),
        workflow_id=overrides.pop("workflow_id", workflow_id),
        batch_id=overrides.pop("batch_id", str(workflow_id) if workflow_id else None),
        details=overrides.pop("details", {}),
        idempotency_key=overrides.pop("idempotency_key", None),
        **overrides,
    )
    session.add(task)
    session.commit()
    return task


class TestReq017SchemaAndEnums:
    def test_task_status_done_is_alias_of_completed(self):
        assert TaskStatus.DONE is TaskStatus.COMPLETED
        assert TaskStatus.DONE.value == "completed"

    def test_required_indexes_exist_on_models(self, db_session):
        inspector = inspect(db_session.bind)
        workflow_indexes = {index["name"] for index in inspector.get_indexes("workflow")}
        execution_indexes = {index["name"] for index in inspector.get_indexes("task_executions")}

        assert "ix_workflow_status" in workflow_indexes
        assert "ix_workflow_epic_id" in workflow_indexes
        assert "ix_workflow_requirement_id" in workflow_indexes
        assert "ix_task_executions_workflow_id" in execution_indexes


class TestReq017Orchestrator:
    def test_prepare_task_reuses_existing_execution(self, db_session, monkeypatch):
        workflow = Workflow(id=uuid4(), status=WorkflowStatus.RUNNING.value)
        db_session.add(workflow)
        db_session.commit()

        task = create_task(
            db_session,
            workflow_id=workflow.id,
            task_number=1,
            status=TaskStatus.QUEUED.value,
            idempotency_key="idem-1",
            details={"scope": "req017"},
        )

        existing_execution = TaskExecution(
            id=uuid4(),
            task_id=task.id,
            workflow_id=workflow.id,
            status=ExecutionStatus.DONE.value,
            result_summary={},
        )
        db_session.add(existing_execution)
        db_session.commit()

        ctx = IdempotencyContext(
            workflow_id=str(workflow.id),
            task_id=task.id,
            task_type=task.type,
            prompt=task.prompt,
            details=task.details,
            idempotency_key=task.idempotency_key,
        )

        orchestrator = Orchestrator()
        monkeypatch.setattr(
            orchestrator.classifier,
            "classify",
            lambda **kwargs: SimpleNamespace(requires_write_access=False),
        )
        orchestrator.workflow_repo.idempotency_service.mark_execution_for_idempotency(
            db_session,
            existing_execution,
            ctx,
        )

        result = orchestrator._prepare_task_context(db_session, task, workflow.id)

        db_session.refresh(task)
        assert result.success is True
        assert result.context is None
        assert task.status == TaskStatus.COMPLETED.value

    def test_process_workflow_group_marks_workflow_done_when_all_tasks_reused(self, db_session, monkeypatch):
        workflow_id = uuid4()
        task = create_task(
            db_session,
            workflow_id=workflow_id,
            task_number=1,
            status=TaskStatus.QUEUED.value,
            idempotency_key="idem-1",
        )
        existing_execution = TaskExecution(
            id=uuid4(),
            task_id=task.id,
            workflow_id=workflow_id,
            status=ExecutionStatus.DONE.value,
            result_summary={},
        )
        db_session.add(existing_execution)
        db_session.commit()

        ctx = IdempotencyContext(
            workflow_id=str(workflow_id),
            task_id=task.id,
            task_type=task.type,
            prompt=task.prompt,
            details=task.details,
            idempotency_key=task.idempotency_key,
        )

        orchestrator = Orchestrator()
        monkeypatch.setattr(
            orchestrator.classifier,
            "classify",
            lambda **kwargs: SimpleNamespace(requires_write_access=False),
        )
        workflow = Workflow(id=workflow_id, status=WorkflowStatus.RUNNING.value)
        db_session.add(workflow)
        db_session.commit()
        monkeypatch.setattr(
            orchestrator.workflow_repo,
            "create_workflow",
            lambda session, ctx: workflow,
        )
        orchestrator.workflow_repo.idempotency_service.mark_execution_for_idempotency(
            db_session,
            existing_execution,
            ctx,
        )

        group = SimpleNamespace(
            group_id=workflow_id,
            tasks=[task],
            group_type="standalone",
            epic_id=None,
            requirement_id=None,
        )

        results = orchestrator._process_workflow_group(db_session, group)

        assert len(results) == 1
        assert workflow.status == WorkflowStatus.DONE.value

    @pytest.mark.asyncio
    async def test_recovery_uses_completed_alias_cleanly(self, db_session):
        workflow = Workflow(id=uuid4(), status=WorkflowStatus.RUNNING.value)
        db_session.add(workflow)
        db_session.commit()
        create_task(db_session, workflow_id=workflow.id, task_number=1, status=TaskStatus.DONE.value)

        orchestrator = Orchestrator()

        await orchestrator.recover_running_workflows(db_session)

        db_session.refresh(workflow)
        assert workflow.status == WorkflowStatus.DONE.value
