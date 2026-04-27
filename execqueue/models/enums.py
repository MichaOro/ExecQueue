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

    Tracks the runtime state of a task execution instance.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


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
