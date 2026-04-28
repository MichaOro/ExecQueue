"""DTOs and models for REQ-011 orchestrator execution preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class BatchType(str, Enum):
    """Types of execution batches based on task characteristics."""
    
    READONLY_PARALLEL = "readonly_parallel"
    WRITE_PARALLEL_ISOLATED = "write_parallel_isolated"
    WRITE_SEQUENTIAL = "write_sequential"


class RunnerMode(str, Enum):
    """Runner modes for execution context."""
    
    READ_ONLY = "read_only"
    WRITE = "write"


class PreparationErrorType(str, Enum):
    """Types of preparation errors for recovery classification."""
    
    RECOVERABLE = "recoverable"
    CONFLICT = "conflict"
    NON_RECOVERABLE = "non_recoverable"


@dataclass(frozen=True)
class TaskClassification:
    """Classification result for a single task.
    
    Attributes:
        task_id: UUID of the task
        task_number: Public task number
        requires_write_access: Whether task needs write access (default True)
        parallelization_mode: 'parallel' or 'sequential'
        effective_runner_mode: Computed runner mode
        conflict_key: Key for conflict grouping (branch, repo, etc.)
        reason_codes: List of reasons for classification decisions
    """
    task_id: UUID
    task_number: int
    requires_write_access: bool = True
    parallelization_mode: str = "sequential"
    effective_runner_mode: RunnerMode = RunnerMode.WRITE
    conflict_key: str | None = None
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BatchPlan:
    """Transient batch plan for execution preparation.
    
    Attributes:
        batch_id: Unique batch identifier
        batch_type: Type of batch (readonly_parallel, write_parallel_isolated, write_sequential)
        task_ids: List of task UUIDs in this batch
        excluded_task_ids: List of excluded task UUIDs
        exclusion_reasons: Reasons for exclusions
        created_at: When the plan was created
    """
    batch_id: str
    batch_type: BatchType
    task_ids: tuple[UUID, ...]
    excluded_task_ids: tuple[UUID, ...] = field(default_factory=tuple)
    exclusion_reasons: dict[UUID, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class PreparedExecutionContext:
    """Versioned context contract for handoff to execution runner.
    
    This is the output of REQ-011 preparation phase. It contains all information
    needed by a downstream runner to start execution, but does NOT start execution itself.
    
    Version: v1
    
    Attributes:
        version: Context version string
        task_id: Task UUID
        task_number: Public task number
        task_type: Task type (planning, execution, analysis)
        requires_write_access: Whether task needs write access
        parallelization_mode: Parallelization mode
        runner_mode: read_only or write
        base_repo_path: Path to base repository
        branch_name: Branch name (nullable for read-only)
        worktree_path: Worktree path (nullable for read-only)
        commit_sha_before: Pre-execution commit SHA (nullable for read-only)
        correlation_id: Correlation ID for tracing
        batch_id: Batch identifier
        prepared_at: When context was prepared
    """
    version: str = "v1"
    task_id: UUID | None = None
    task_number: int | None = None
    task_type: str | None = None
    requires_write_access: bool = True
    parallelization_mode: str = "sequential"
    runner_mode: RunnerMode = RunnerMode.WRITE
    base_repo_path: str | None = None
    branch_name: str | None = None
    worktree_path: str | None = None
    commit_sha_before: str | None = None
    correlation_id: str | None = None
    batch_id: str | None = None
    prepared_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "task_id": str(self.task_id) if self.task_id else None,
            "task_number": self.task_number,
            "task_type": self.task_type,
            "requires_write_access": self.requires_write_access,
            "parallelization_mode": self.parallelization_mode,
            "runner_mode": self.runner_mode.value,
            "base_repo_path": self.base_repo_path,
            "branch_name": self.branch_name,
            "worktree_path": self.worktree_path,
            "commit_sha_before": self.commit_sha_before,
            "correlation_id": self.correlation_id,
            "batch_id": self.batch_id,
            "prepared_at": self.prepared_at.isoformat() if self.prepared_at else None,
        }
    
    def validate(self) -> list[str]:
        """Validate context and return list of error messages."""
        errors = []
        
        if self.runner_mode == RunnerMode.WRITE:
            if not self.branch_name:
                errors.append("WRITE mode requires branch_name")
            if not self.worktree_path:
                errors.append("WRITE mode requires worktree_path")
            if not self.commit_sha_before:
                errors.append("WRITE mode requires commit_sha_before")
        
        if not self.base_repo_path:
            errors.append("base_repo_path is required")
        
        return errors


class PreparationError(Exception):
    """Preparation error with classification for recovery.
    
    Attributes:
        error_type: Type of error (recoverable, conflict, non_recoverable)
        message: Human-readable error message
        task_id: Affected task UUID
        details: Additional error details
    """
    
    def __init__(
        self,
        error_type: PreparationErrorType,
        message: str,
        task_id: UUID,
        details: dict[str, Any] | None = None,
    ):
        """Initialize error.
        
        Args:
            error_type: Type of error
            message: Error message
            task_id: Affected task UUID
            details: Additional error details
        """
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.task_id = task_id
        self.details = details or {}
    
    def is_recoverable(self) -> bool:
        """Check if error is recoverable."""
        return self.error_type == PreparationErrorType.RECOVERABLE
    
    def is_conflict(self) -> bool:
        """Check if error is a conflict."""
        return self.error_type == PreparationErrorType.CONFLICT
    
    def is_non_recoverable(self) -> bool:
        """Check if error is non-recoverable."""
        return self.error_type == PreparationErrorType.NON_RECOVERABLE
