"""ExecQueue ORM models package.

This package contains additional SQLAlchemy ORM models for the ExecQueue
persistent execution data model, specifically for execution tracking.

Note: The core Requirement and Task models are defined in execqueue/db/models.py
and should be imported from there.

Models in this package:
    ExecutionPlan: Execution plan for a requirement
    TaskDependency: Dependency relationship between tasks
    TaskExecution: Execution run of a task
    TaskExecutionEvent: Event generated during execution

Enums:
    ExecutionStatus: Execution run states
    EventDirection: Event direction (inbound/outbound)
    EventType: Types of execution events

Usage:
    from execqueue.db.models import Requirement, Task
    from execqueue.models import ExecutionPlan, TaskExecution
    from execqueue.models.enums import ExecutionStatus
"""

from execqueue.db.base import Base

# Import enums specific to execution tracking
from execqueue.models.enums import (
    EventDirection,
    EventType,
    ExecutionStatus,
)

# Import execution-related models only
from execqueue.models.execution_plan import ExecutionPlan
from execqueue.models.task_dependency import TaskDependency
from execqueue.models.task_execution import TaskExecution
from execqueue.models.task_execution_event import TaskExecutionEvent

__all__ = [
    # Base
    "Base",
    # Enums
    "ExecutionStatus",
    "EventDirection",
    "EventType",
    # Models (execution-related only)
    "ExecutionPlan",
    "TaskDependency",
    "TaskExecution",
    "TaskExecutionEvent",
]
