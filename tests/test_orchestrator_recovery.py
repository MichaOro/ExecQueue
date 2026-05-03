from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task, TaskStatus
from execqueue.orchestrator.main import Orchestrator
from execqueue.orchestrator.runner_manager import RunnerHandle
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


def create_task(
    session,
    workflow_id,
    task_number: int,
    status: str,
):
    task = Task(
        task_number=task_number,
        title=f"Task {task_number}",
        prompt="Test prompt",
        type="execution",
        status=status,
        created_by_type="agent",
        created_by_ref="test",
        max_retries=3,
        workflow_id=workflow_id,
        batch_id=str(workflow_id),
        details={},
    )
    session.add(task)
    session.commit()
    return task


class TestCrashRecovery:
    @pytest.mark.asyncio
    async def test_recovery_marks_workflow_done_when_all_tasks_completed(self, db_session):
        workflow = Workflow(id=uuid4(), status=WorkflowStatus.RUNNING.value)
        db_session.add(workflow)
        db_session.commit()

        create_task(db_session, workflow.id, 1, TaskStatus.COMPLETED.value)
        create_task(db_session, workflow.id, 2, TaskStatus.COMPLETED.value)

        orchestrator = Orchestrator()

        await orchestrator.recover_running_workflows(db_session)

        db_session.refresh(workflow)
        assert workflow.status == WorkflowStatus.DONE.value

    @pytest.mark.asyncio
    async def test_recovery_marks_workflow_done_when_no_tasks_exist(self, db_session):
        workflow = Workflow(id=uuid4(), status=WorkflowStatus.RUNNING.value)
        db_session.add(workflow)
        db_session.commit()

        orchestrator = Orchestrator()

        await orchestrator.recover_running_workflows(db_session)

        db_session.refresh(workflow)
        assert workflow.status == WorkflowStatus.DONE.value

    @pytest.mark.asyncio
    async def test_recovery_restarts_runner_for_pending_tasks(self, db_session, monkeypatch):
        workflow = Workflow(id=uuid4(), status=WorkflowStatus.RUNNING.value, runner_uuid="lost-runner")
        db_session.add(workflow)
        db_session.commit()

        pending = create_task(db_session, workflow.id, 1, TaskStatus.PREPARED.value)
        create_task(db_session, workflow.id, 2, TaskStatus.COMPLETED.value)

        orchestrator = Orchestrator()

        started_contexts = []

        def fake_start_runner(ctx, runner_class=None):
            started_contexts.append(ctx)
            return RunnerHandle(runner_uuid="runner-new", workflow_id=ctx.workflow_id, task=None)

        monkeypatch.setattr(orchestrator.runner_manager, "start_runner_for_context", fake_start_runner)
        monkeypatch.setattr(orchestrator.runner_manager, "get_runner_handle", lambda workflow_id: None)

        await orchestrator.recover_running_workflows(db_session)

        db_session.refresh(workflow)
        assert workflow.runner_uuid == "runner-new"
        assert len(started_contexts) == 1
        assert started_contexts[0].workflow_id == workflow.id
        assert [task.task_id for task in started_contexts[0].tasks] == [pending.id]

    @pytest.mark.asyncio
    async def test_recovery_skips_workflow_with_active_runner(self, db_session, monkeypatch):
        workflow = Workflow(id=uuid4(), status=WorkflowStatus.RUNNING.value, runner_uuid="active-runner")
        db_session.add(workflow)
        db_session.commit()
        create_task(db_session, workflow.id, 1, TaskStatus.PREPARED.value)

        orchestrator = Orchestrator()

        handle = RunnerHandle(runner_uuid="active-runner", workflow_id=workflow.id, task=None)
        monkeypatch.setattr(orchestrator.runner_manager, "get_runner_handle", lambda workflow_id: handle)

        started = False

        def fake_start_runner(ctx, runner_class=None):
            nonlocal started
            started = True
            return RunnerHandle(runner_uuid="unexpected", workflow_id=ctx.workflow_id, task=None)

        monkeypatch.setattr(orchestrator.runner_manager, "start_runner_for_context", fake_start_runner)

        await orchestrator.recover_running_workflows(db_session)

        assert started is False
