"""REQ-011 Orchestrator for Execution Preparation.

This module implements the orchestrator execution preparation flow as specified
in REQ-011. It handles:

1. Candidate Discovery - Loading executable backlog tasks from DB
2. Task Classification - Determining read-only vs write, parallel vs sequential
3. Batch Planning - Creating safe execution batches
4. Atomic Locking - Claiming tasks with backlog->queued transition
5. Git Context Preparation - Branch/Worktree setup for write tasks
6. Context Contract - Building PreparedExecutionContext for handoff

Scope: REQ-011 ends at prepared_context_available. It does NOT start OpenCode sessions
or transition tasks to in_progress.

Note: This module coexists with the legacy orchestrator_legacy.py which handles
local process management (API + Telegram bot).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

# Import legacy orchestrator components (for local process management)
from execqueue.orchestrator_legacy import (
    LaunchPlan,
    ManagedProcess,
    build_launch_plan,
    monitor_processes,
    run_orchestrator,
    spawn_process,
    terminate_process,
)

# Import REQ-011 components
from execqueue.orchestrator.candidate_discovery import CandidateDiscovery
from execqueue.orchestrator.classification import TaskClassifier, BatchPlanner
from execqueue.orchestrator.locking import TaskLocker
from execqueue.orchestrator.git_context import GitContextPreparer
from execqueue.orchestrator.context_contract import PreparedContextBuilder
from execqueue.orchestrator.main import Orchestrator
from execqueue.orchestrator.exceptions import (
    OrchestratorError,
    DependencyError,
    CycleError,
    ValidationError,
    CandidateDiscoveryError,
    LockingError,
    ContextBuildingError,
)
from execqueue.orchestrator.models import (
    BatchPlan,
    BatchType,
    PreparedExecutionContext,
    PreparationError,
    PreparationErrorType,
    RunnerMode,
    TaskClassification,
)
from execqueue.orchestrator.recovery import (
    PreparationErrorClassifier,
    StaleQueuedRecovery,
)
from execqueue.orchestrator.observability import (
    E2EValidator,
    StructuredLogger,
    create_e2e_validator,
)

__all__ = [
    # Legacy components (local process management) - re-exported for backward compatibility
    "LaunchPlan",
    "ManagedProcess",
    "build_launch_plan",
    "monitor_processes",
    "run_orchestrator",
    "spawn_process",
    "terminate_process",
    # REQ-011 components
    "Orchestrator",
    "CandidateDiscovery",
    "TaskClassifier",
    "BatchPlanner",
    "TaskLocker",
    "GitContextPreparer",
    "PreparedContextBuilder",
    "PreparationErrorClassifier",
    "StaleQueuedRecovery",
    "StructuredLogger",
    "E2EValidator",
    "create_e2e_validator",
    # Models
    "BatchPlan",
    "BatchType",
    "PreparedExecutionContext",
    "PreparationError",
    "PreparationErrorType",
    "RunnerMode",
    "TaskClassification",
    # Exception hierarchy
    "OrchestratorError",
    "DependencyError",
    "CycleError",
    "ValidationError",
    "CandidateDiscoveryError",
    "LockingError",
    "ContextBuildingError",
]

logger = logging.getLogger(__name__)
