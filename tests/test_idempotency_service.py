from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.db.base import Base
from execqueue.db.models import Task
from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.orchestrator.idempotency_service import IdempotencyContext, IdempotencyService
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


class TestIdempotencyContext:
    def test_hash_is_deterministic(self):
        ctx = IdempotencyContext(
            workflow_id=str(uuid4()),
            task_id=uuid4(),
            task_type="execution",
            prompt="Prompt",
            details={"a": 1, "b": ["x", "y"]},
            idempotency_key="idem-1",
        )

        assert ctx.compute_input_hash() == ctx.compute_input_hash()
        assert len(ctx.compute_input_hash()) == 64

    def test_different_inputs_change_hash(self):
        workflow_id = str(uuid4())
        task_id = uuid4()

        ctx1 = IdempotencyContext(workflow_id, task_id, "execution", "Prompt A", {}, "idem-1")
        ctx2 = IdempotencyContext(workflow_id, task_id, "execution", "Prompt B", {}, "idem-1")

        assert ctx1.compute_input_hash() != ctx2.compute_input_hash()


class TestIdempotencyService:
    def test_detects_duplicate_execution(self, db_session):
        service = IdempotencyService()
        workflow_id = uuid4()
        task_id = uuid4()
        ctx = IdempotencyContext(
            workflow_id=str(workflow_id),
            task_id=task_id,
            task_type="execution",
            prompt="Prompt",
            details={"x": 1},
            idempotency_key="idem-1",
        )

        execution = TaskExecution(
            id=uuid4(),
            task_id=task_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.DONE.value,
            result_summary={
                "input_hash": ctx.compute_input_hash(),
                "idempotency_key": "idem-1",
            },
        )
        db_session.add(execution)
        db_session.commit()

        assert service.is_task_already_done(db_session, ctx).id == execution.id

    def test_ignores_execution_with_different_idempotency_key(self, db_session):
        service = IdempotencyService()
        workflow_id = uuid4()
        task_id = uuid4()
        ctx = IdempotencyContext(
            workflow_id=str(workflow_id),
            task_id=task_id,
            task_type="execution",
            prompt="Prompt",
            details={},
            idempotency_key="idem-new",
        )

        execution = TaskExecution(
            id=uuid4(),
            task_id=task_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.DONE.value,
            result_summary={
                "input_hash": ctx.compute_input_hash(),
                "idempotency_key": "idem-old",
            },
        )
        db_session.add(execution)
        db_session.commit()

        assert service.is_task_already_done(db_session, ctx) is None

    def test_marks_execution_for_idempotency(self, db_session):
        service = IdempotencyService()
        workflow_id = uuid4()
        task_id = uuid4()
        ctx = IdempotencyContext(
            workflow_id=str(workflow_id),
            task_id=task_id,
            task_type="execution",
            prompt="Prompt",
            details={"x": 1},
            idempotency_key="idem-1",
        )

        execution = TaskExecution(
            id=uuid4(),
            task_id=task_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.DONE.value,
            result_summary={},
        )
        db_session.add(execution)
        db_session.commit()

        service.mark_execution_for_idempotency(db_session, execution, ctx)
        db_session.refresh(execution)

        assert execution.result_summary["input_hash"] == ctx.compute_input_hash()
        assert execution.result_summary["idempotency_key"] == "idem-1"
