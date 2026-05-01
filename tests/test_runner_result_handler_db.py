from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task, TaskStatus
from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent
from execqueue.orchestrator.workflow_models import Workflow, WorkflowStatus
from execqueue.runner.result_handler import ResultHandler
from execqueue.runner.workflow_executor import TaskResult


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


@pytest.fixture
def workflow(db_session):
    workflow = Workflow(id=uuid4(), status=WorkflowStatus.RUNNING.value)
    db_session.add(workflow)
    db_session.commit()
    return workflow


@pytest.fixture
def prepared_tasks(db_session, workflow):
    tasks: list[Task] = []
    for idx in range(3):
        task = Task(
            task_number=idx + 1,
            title=f"Task {idx + 1}",
            prompt="Test prompt",
            type="execution",
            status=TaskStatus.PREPARED.value,
            max_retries=3,
            created_by_type="agent",
            created_by_ref="test",
            workflow_id=workflow.id,
            batch_id=str(workflow.id),
            details={},
        )
        db_session.add(task)
        tasks.append(task)
    db_session.commit()
    return tasks


@pytest.fixture
def task_executions(db_session, workflow, prepared_tasks):
    executions: list[TaskExecution] = []
    for task in prepared_tasks:
        execution = TaskExecution(
            id=uuid4(),
            task_id=task.id,
            workflow_id=workflow.id,
            status=ExecutionStatus.QUEUED.value,
        )
        db_session.add(execution)
        executions.append(execution)
    db_session.commit()
    return executions


class TestResultHandlerDBPersistence:
    def test_persist_single_result_updates_execution(self, db_session, workflow, task_executions):
        handler = ResultHandler(db_session)
        execution = task_executions[0]

        handler.persist_results(
            workflow.id,
            [
                TaskResult(
                    task_id=execution.task_id,
                    status="DONE",
                    commit_sha="abc123",
                    worktree_path="/tmp/worktree",
                    opencode_session_id="sess-1",
                    duration_seconds=10.5,
                )
            ],
        )

        db_session.refresh(execution)
        assert execution.status == "done"
        assert execution.commit_sha_after == "abc123"
        assert execution.result_summary["duration_seconds"] == 10.5

    def test_persist_logs_execution_event(self, db_session, workflow, task_executions):
        handler = ResultHandler(db_session)
        execution = task_executions[0]

        handler.persist_results(workflow.id, [TaskResult(task_id=execution.task_id, status="DONE")])

        events = db_session.query(TaskExecutionEvent).filter(
            TaskExecutionEvent.task_execution_id == execution.id
        ).all()

        assert len(events) == 1
        assert events[0].event_type == "status_update"
        assert events[0].payload["status"] == "DONE"

    def test_workflow_becomes_done_when_all_executions_done(self, db_session, workflow, task_executions):
        handler = ResultHandler(db_session)

        results = [TaskResult(task_id=execution.task_id, status="DONE") for execution in task_executions]
        handler.persist_results(workflow.id, results)

        db_session.refresh(workflow)
        assert workflow.status == WorkflowStatus.DONE.value
        assert handler.aggregate_workflow_status(workflow.id) == WorkflowStatus.DONE.value

    def test_workflow_becomes_failed_when_any_execution_fails(self, db_session, workflow, task_executions):
        handler = ResultHandler(db_session)

        results = [
            TaskResult(task_id=task_executions[0].task_id, status="DONE"),
            TaskResult(task_id=task_executions[1].task_id, status="FAILED", error_message="boom"),
        ]
        handler.persist_results(workflow.id, results)

        db_session.refresh(workflow)
        assert workflow.status == WorkflowStatus.FAILED.value
        assert handler.aggregate_workflow_status(workflow.id) == WorkflowStatus.FAILED.value

    def test_retry_keeps_workflow_running(self, db_session, workflow, task_executions):
        handler = ResultHandler(db_session)

        handler.persist_results(workflow.id, [TaskResult(task_id=task_executions[0].task_id, status="RETRY")])

        db_session.refresh(workflow)
        db_session.refresh(task_executions[0])
        assert workflow.status == WorkflowStatus.RUNNING.value
        assert task_executions[0].status == ExecutionStatus.PREPARED.value
