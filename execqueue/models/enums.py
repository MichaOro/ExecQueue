"""Enum types for ExecQueue execution tracking models.

This module defines enumeration types used specifically for execution
tracking in the ExecQueue data model.

Note: Core enums (RequirementStatus, TaskStatus, TaskType) are defined
in execqueue/db/models.py and should be imported from there.

Enums:
    ExecutionStatus: Execution run states
    EventDirection: Event direction (inbound/outbound)
    EventType: Types of execution events
"""

from enum import Enum


class ExecutionStatus(str, Enum):
    """Execution run states.

    Tracks the runtime state of a task execution instance with granular
    status values for REQ-012 runner lifecycle.
    """

    PREPARED = "prepared"
    QUEUED = "queued"
    DISPATCHING = "dispatching"
    IN_PROGRESS = "in_progress"
    RESULT_INSPECTION = "result_inspection"
    ADOPTING_COMMIT = "adopting_commit"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


# Status groupings for consistent usage across model constraints and application code
# These constants eliminate duplication and ensure consistency between database
# constraints and application-level checks (REQ-012 quality improvement)
FINAL_EXECUTION_STATUSES = ("done", "failed", "review")
"""Terminal execution states that do not count as active."""

ACTIVE_EXECUTION_STATUSES = ("prepared", "queued", "dispatching", "in_progress", "result_inspection", "adopting_commit")
"""Active execution states that count as in-progress."""


class EventDirection(str, Enum):
    """Direction of execution events.

    Indicates whether an event is incoming (from external source)
    or outgoing (to external system).
    """

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EventType(str, Enum):
    """Types of execution events.

    Categorizes the nature of an event in the execution lifecycle.
    """

    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    ERROR = "error"
    STATUS_UPDATE = "status_update"
    EXECUTION_CLAIMED = "execution.claimed"
    EXECUTION_DISPATCHED = "execution.dispatched"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    SESSION_CREATED = "session.created"
    SESSION_CLOSED = "session.closed"
    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"
    STREAM_CONNECTED = "stream.connected"
    STREAM_DISCONNECTED = "stream.disconnected"
    STREAM_HEARTBEAT = "stream.heartbeat"
    RESULT_INSPECTED = "result.inspected"
    COMMIT_ADOPTION_STARTED = "commit.adoption_started"
    COMMIT_ADOPTION_SUCCESS = "commit.adoption_success"
    COMMIT_ADOPTION_CONFLICT = "commit.adoption_conflict"
    RETRY_SCHEDULED = "retry.scheduled"
    RETRY_EXHAUSTED = "retry.exhausted"
