"""Prompt dispatch service for REQ-012-05.

This module implements the prompt dispatch logic that:
- Converts PreparedExecutionContext to OpenCode prompts
- Manages status transitions: queued -> dispatching -> in_progress
- Persists dispatch events with metadata
- Handles errors without setting in_progress on failure
- Per REQ-012-10: Structured logging with correlation IDs
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from execqueue.db.models import Task, TaskStatus
from execqueue.models.enums import EventType, ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent
from execqueue.opencode.client import (
    OpenCodeClient,
    OpenCodeMessage,
    OpenCodeValidationError,
)
from execqueue.orchestrator.models import PreparedExecutionContext
from execqueue.observability import (
    get_logger,
    log_phase_event,
    measure_phase,
    record_execution_failed,
    redact_payload,
)
from execqueue.runner.prompt_templates import build_prompt

logger = logging.getLogger(__name__)
obs_logger = get_logger(__name__)


class DispatchError(Exception):
    """Raised when prompt dispatch fails."""

    def __init__(
        self,
        message: str,
        cause: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        self.cause = cause
        self.context = context or {}
        super().__init__(message)


class PromptDispatcher:
    """Service for dispatching prompts to OpenCode.

    This service handles the transition from prepared context to in_progress
    status, ensuring that in_progress is only set after successful dispatch.
    Per REQ-012-10: Logs with correlation ID and structured format.
    """

    def __init__(self, opencode_client: OpenCodeClient | None = None):
        """Initialize the dispatcher.

        Args:
            opencode_client: OpenCode client instance (creates default if None)
        """
        self.opencode_client = opencode_client or OpenCodeClient()

    async def dispatch_prompt(
        self,
        session: Session,
        execution_id: UUID,
        context: PreparedExecutionContext,
        task_prompt: str,
    ) -> tuple[TaskExecution, OpenCodeMessage]:
        """Dispatch a prompt to OpenCode and update status.

        This method implements the REQ-012-05 flow:
        1. Set status to 'dispatching'
        2. Build prompt from context
        3. Dispatch to OpenCode
        4. On success: set status to 'in_progress', persist message ID
        5. On failure: keep status as 'dispatching' or 'queued', log error
        6. Per REQ-012-10: Logs with correlation ID and timing metrics

        Args:
            session: Database session
            execution_id: TaskExecution ID to dispatch
            context: PreparedExecutionContext for prompt building
            task_prompt: Original task prompt

        Returns:
            Tuple of (updated TaskExecution, OpenCodeMessage)

        Raises:
            DispatchError: If dispatch fails
        """
        # Get the execution
        execution = session.get(TaskExecution, execution_id)
        if not execution:
            raise DispatchError(f"TaskExecution {execution_id} not found")

        correlation_id = execution.correlation_id or "unknown"
        task_id_str = str(execution.task_id)
        execution_id_str = str(execution_id)

        # Verify execution is in queued state
        if execution.status != ExecutionStatus.QUEUED.value:
            raise DispatchError(
                f"Execution must be in 'queued' state, current: {execution.status}"
            )

        # Step 1: Set status to 'dispatching'
        execution.status = ExecutionStatus.DISPATCHING.value
        execution.started_at = datetime.now(timezone.utc)
        session.flush()  # Flush to persist status change

        # Log dispatch start with structured data
        log_phase_event(
            obs_logger,
            f"Dispatching prompt for execution {execution_id_str}, task {task_id_str}",
            correlation_id=correlation_id,
            execution_id=execution_id_str,
            task_id=task_id_str,
            runner_id=execution.runner_id,
            phase="dispatch",
            opencode_session_id=execution.opencode_session_id,
        )

        # Use phase timer for metrics
        with measure_phase("dispatch", correlation_id, obs_logger) as phase_metrics:
            try:
                # Step 2: Build prompt from context
                context_dict = context.to_dict()
                context_dict["task_prompt"] = task_prompt

                # Redact sensitive data from context before logging
                redacted_context = redact_payload(context_dict)

                prompt = build_prompt(context_dict)

                # Add full prompt to context for OpenCode
                # Note: We do NOT store the full prompt in DB (too large, potential secrets)
                # Instead, we store a hash or reference
                prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
                log_phase_event(
                    obs_logger,
                    f"Built prompt (hash: {prompt_hash}) for execution {execution_id_str}",
                    correlation_id=correlation_id,
                    execution_id=execution_id_str,
                    task_id=task_id_str,
                    runner_id=execution.runner_id,
                    phase="dispatch",
                    prompt_hash=prompt_hash,
                )

                # Step 3: Dispatch to OpenCode
                # Use the context as session name for traceability
                session_name = f"execqueue-task-{context.task_number}-v{context.version}"
                opencode_session = await self.opencode_client.create_session(
                    name=session_name
                )

                # Dispatch the message
                message = await self.opencode_client.dispatch_message(
                    session_id=opencode_session.id,
                    content=prompt,
                    role="user",
                )

                # Step 4: On success - set status to 'in_progress'
                execution.status = ExecutionStatus.IN_PROGRESS.value
                execution.dispatched_at = datetime.now(timezone.utc)
                execution.opencode_session_id = opencode_session.id
                execution.opencode_message_id = message.id

                # Store minimal context reference (not full prompt)
                execution.result_summary = {
                    "prompt_hash": prompt_hash,
                    "context_version": context.version,
                    "runner_mode": context.runner_mode.value,
                    "dispatched_at": execution.dispatched_at.isoformat(),
                }

                # Persist the event with correlation ID
                event = TaskExecutionEvent(
                    task_execution_id=execution_id,
                    sequence=self._get_next_sequence(session, execution_id),
                    correlation_id=correlation_id,  # REQ-012-10: Propagate correlation ID
                    event_type=EventType.EXECUTION_DISPATCHED.value,
                    payload={
                        "opencode_session_id": opencode_session.id,
                        "opencode_message_id": message.id,
                        "prompt_hash": prompt_hash,
                        "context_version": context.version,
                        "runner_mode": context.runner_mode.value,
                        "dispatched_at": execution.dispatched_at.isoformat(),
                    },
                    created_at=datetime.now(timezone.utc),
                    direction="outbound",
                )
                session.add(event)

                log_phase_event(
                    obs_logger,
                    f"Successfully dispatched prompt for execution {execution_id_str}, "
                    f"message {message.id}",
                    correlation_id=correlation_id,
                    execution_id=execution_id_str,
                    task_id=task_id_str,
                    runner_id=execution.runner_id,
                    phase="dispatch",
                    session_id=opencode_session.id,
                    message_id=message.id,
                )

                # Record phase duration metric
                from execqueue.observability import record_phase_duration, record_execution_completed

                record_phase_duration("dispatch", phase_metrics.duration_seconds)

                return execution, message

            except Exception as e:
                # Step 5: On failure - do NOT set in_progress
                error_msg = str(e)

                # Log the error with structured data
                log_phase_event(
                    obs_logger,
                    f"Failed to dispatch prompt for execution {execution_id_str}: {error_msg}",
                    correlation_id=correlation_id,
                    execution_id=execution_id_str,
                    task_id=task_id_str,
                    runner_id=execution.runner_id,
                    phase="dispatch",
                    level=logging.ERROR,
                    error_type=type(e).__name__,
                )

                # Update execution with error info
                execution.error_type = type(e).__name__
                execution.error_message = error_msg

                # Persist error event with correlation ID
                event = TaskExecutionEvent(
                    task_execution_id=execution_id,
                    sequence=self._get_next_sequence(session, execution_id),
                    correlation_id=correlation_id,  # REQ-012-10: Propagate correlation ID
                    event_type=EventType.ERROR.value,
                    payload={
                        "error_type": type(e).__name__,
                        "error_message": error_msg,
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                        "phase": "prompt_dispatch",
                    },
                    created_at=datetime.now(timezone.utc),
                    direction="outbound",
                )
                session.add(event)

                # Record failure metric
                record_execution_failed()

                # Raise as DispatchError for caller handling
                raise DispatchError(
                    f"Failed to dispatch prompt: {error_msg}",
                    cause=e,
                    context={
                        "execution_id": execution_id_str,
                        "task_id": task_id_str,
                        "context_version": context.version,
                    },
                ) from e

    def _get_next_sequence(self, session: Session, execution_id: UUID) -> int:
        """Get the next sequence number for an execution's events.

        Args:
            session: Database session
            execution_id: TaskExecution ID

        Returns:
            Next sequence number (1 if no events exist)
        """
        max_seq = session.execute(
            select(func.max(TaskExecutionEvent.sequence)).where(
                TaskExecutionEvent.task_execution_id == execution_id
            )
        ).scalar()

        return (max_seq or 0) + 1


# Import func for convenience
