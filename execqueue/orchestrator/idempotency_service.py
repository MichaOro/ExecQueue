"""Idempotency service for workflow task execution.

Implements REQ-017 PERS-008, PERS-009.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution


@dataclass(frozen=True)
class IdempotencyContext:
    """Context for idempotency calculation."""

    workflow_id: str
    task_id: UUID
    task_type: str
    prompt: str
    details: dict[str, Any]
    idempotency_key: str | None = None

    def compute_input_hash(self) -> str:
        """Compute deterministic SHA-256 hash from inputs.

        Returns:
            Hex-encoded SHA-256 hash (64 characters)
        """
        canonical = {
            "workflow_id": self.workflow_id,
            "task_id": str(self.task_id),
            "task_type": self.task_type,
            "prompt": self.prompt,
            "details": json.dumps(self.details, sort_keys=True),
            "idempotency_key": self.idempotency_key,
        }
        payload = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class IdempotencyService:
    """Service for checking and managing task execution idempotency."""

    def __init__(self):
        """Initialize the service."""
        pass

    def is_task_already_done(
        self,
        session: Session,
        ctx: IdempotencyContext,
    ) -> TaskExecution | None:
        """Check if a task with identical inputs was already executed.

        Args:
            session: Database session
            ctx: Idempotency context containing workflow_id, task_id, and inputs

        Returns:
            Existing TaskExecution if found with matching hash, None otherwise
        """
        input_hash = ctx.compute_input_hash()

        # Search for completed execution with matching hash
        stmt = (
            select(TaskExecution)
            .where(TaskExecution.workflow_id == UUID(ctx.workflow_id))
            .where(TaskExecution.task_id == ctx.task_id)
            .where(TaskExecution.status == ExecutionStatus.DONE.value)
            .where(TaskExecution.result_summary.isnot(None))
        )
        results = session.execute(stmt).scalars().all()

        for execution in results:
            result_summary = execution.result_summary or {}
            stored_hash = result_summary.get("input_hash")
            stored_key = result_summary.get("idempotency_key")
            if ctx.idempotency_key and stored_key != ctx.idempotency_key:
                continue
            if stored_hash == input_hash:
                return execution

        return None

    def mark_execution_for_idempotency(
        self,
        session: Session,
        execution: TaskExecution,
        ctx: IdempotencyContext,
    ) -> None:
        """Store input_hash in execution result_summary.

        Args:
            session: Database session
            execution: TaskExecution to update
            ctx: Idempotency context
        """
        if execution.result_summary is None:
            execution.result_summary = {}

        execution.result_summary["input_hash"] = ctx.compute_input_hash()
        execution.result_summary["idempotency_key"] = ctx.idempotency_key
        flag_modified(execution, "result_summary")
        session.commit()
