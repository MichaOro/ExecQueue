"""Error classification and retry policy for REQ-012-09.

This module provides:
- Error type classification (transient, permanent, conflict, timeout, contract_violation, validation_failed)
- Retry matrix per runner phase (claim/session/dispatch/stream/result/adoption)
- Backoff calculation and retry scheduling
- Stale execution detection
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from execqueue.models.enums import ExecutionStatus, EventType
from execqueue.models.task_execution import TaskExecution

logger = logging.getLogger(__name__)


# ============================================================================
# Error Type Enumeration
# ============================================================================


class ErrorType(str, Enum):
    """Classified error types for retry decisions.

    Per REQ-012-09 Technical Specification:
    - transient: Temporary failures that may resolve (network, resource exhaustion)
    - permanent: Irrecoverable failures (invalid data, permission denied)
    - conflict: Git/state conflicts requiring manual intervention
    - timeout: Operation exceeded time limit
    - contract_violation: Protocol/API contract violation
    - validation_failed: Input/validation error
    """

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    CONFLICT = "conflict"
    TIMEOUT = "timeout"
    CONTRACT_VIOLATION = "contract_violation"
    VALIDATION_FAILED = "validation_failed"

    @property
    def is_retryable(self) -> bool:
        """Check if this error type allows retry."""
        return self in (
            ErrorType.TRANSIENT,
            ErrorType.TIMEOUT,
        )

    @property
    def severity(self) -> int:
        """Return severity level (higher = more severe)."""
        severity_map = {
            ErrorType.TRANSIENT: 1,
            ErrorType.TIMEOUT: 2,
            ErrorType.VALIDATION_FAILED: 3,
            ErrorType.CONTRACT_VIOLATION: 4,
            ErrorType.CONFLICT: 5,
            ErrorType.PERMANENT: 6,
        }
        return severity_map[self]


# ============================================================================
# Runner Phases
# ============================================================================


class RunnerPhase(str, Enum):
    """Runner execution phases for retry matrix."""

    CLAIM = "claim"
    SESSION = "session"
    DISPATCH = "dispatch"
    STREAM = "stream"
    RESULT = "result"
    ADOPTION = "adoption"


# ============================================================================
# Retry Policy Configuration
# ============================================================================


@dataclass
class PhaseRetryPolicy:
    """Retry policy for a specific phase."""

    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    backoff_multiplier: float = 2.0
    jitter_factor: float = 0.1  # Random jitter 0-10%


@dataclass
class RetryMatrix:
    """Retry policies per runner phase.

    Per REQ-012-09: Retry-Matrix je Phase: claim/session/dispatch/stream/result/adoption
    """

    claim: PhaseRetryPolicy = field(
        default_factory=lambda: PhaseRetryPolicy(
            max_attempts=3,
            base_delay_seconds=1.0,
            max_delay_seconds=30.0,
        )
    )
    session: PhaseRetryPolicy = field(
        default_factory=lambda: PhaseRetryPolicy(
            max_attempts=3,
            base_delay_seconds=2.0,
            max_delay_seconds=60.0,
        )
    )
    dispatch: PhaseRetryPolicy = field(
        default_factory=lambda: PhaseRetryPolicy(
            max_attempts=3,
            base_delay_seconds=5.0,
            max_delay_seconds=120.0,
        )
    )
    stream: PhaseRetryPolicy = field(
        default_factory=lambda: PhaseRetryPolicy(
            max_attempts=2,
            base_delay_seconds=10.0,
            max_delay_seconds=300.0,
        )
    )
    result: PhaseRetryPolicy = field(
        default_factory=lambda: PhaseRetryPolicy(
            max_attempts=2,
            base_delay_seconds=5.0,
            max_delay_seconds=120.0,
        )
    )
    adoption: PhaseRetryPolicy = field(
        default_factory=lambda: PhaseRetryPolicy(
            max_attempts=2,
            base_delay_seconds=10.0,
            max_delay_seconds=300.0,
        )
    )

    def get_policy(self, phase: RunnerPhase) -> PhaseRetryPolicy:
        """Get retry policy for a phase."""
        policy_map = {
            RunnerPhase.CLAIM: self.claim,
            RunnerPhase.SESSION: self.session,
            RunnerPhase.DISPATCH: self.dispatch,
            RunnerPhase.STREAM: self.stream,
            RunnerPhase.RESULT: self.result,
            RunnerPhase.ADOPTION: self.adoption,
        }
        return policy_map.get(phase, self.dispatch)


# Default retry matrix instance
DEFAULT_RETRY_MATRIX = RetryMatrix()


# ============================================================================
# Error Classification Functions
# ============================================================================


def classify_error(
    exception: Exception,
    phase: RunnerPhase | None = None,
    context: dict | None = None,
) -> ErrorType:
    """Classify an exception into an error type.

    Per REQ-012-09: Fehlerkonsistente Klassifizierung.

    Args:
        exception: The exception to classify
        phase: Optional runner phase context
        context: Optional additional context for classification

    Returns:
        Classified ErrorType
    """
    import httpx

    error_msg = str(exception).lower()

    # Timeout detection
    if isinstance(exception, asyncio.TimeoutError):
        return ErrorType.TIMEOUT
    if isinstance(exception, httpx.TimeoutException):
        return ErrorType.TIMEOUT
    if "timeout" in error_msg or "timed out" in error_msg:
        return ErrorType.TIMEOUT

    # Connection/transient errors
    if isinstance(exception, (ConnectionError, ConnectionRefusedError, ConnectionResetError)):
        return ErrorType.TRANSIENT
    if isinstance(exception, httpx.ConnectError):
        return ErrorType.TRANSIENT
    if "connection" in error_msg and "refused" in error_msg:
        return ErrorType.TRANSIENT
    if "network" in error_msg or "unreachable" in error_msg:
        return ErrorType.TRANSIENT

    # Conflict errors (Git conflicts, state conflicts)
    if isinstance(exception, ConflictError):
        return ErrorType.CONFLICT
    if "conflict" in error_msg:
        return ErrorType.CONFLICT
    if "merge conflict" in error_msg or "already exists" in error_msg:
        return ErrorType.CONFLICT

    # Validation errors
    if isinstance(exception, (ValueError, ValidationError)):
        return ErrorType.VALIDATION_FAILED
    if "validation" in error_msg or "invalid" in error_msg:
        if "conflict" not in error_msg:  # Don't misclassify conflicts
            return ErrorType.VALIDATION_FAILED

    # Contract violations (API violations, schema mismatches)
    if isinstance(exception, ContractViolationError):
        return ErrorType.CONTRACT_VIOLATION
    if "contract" in error_msg or "schema" in error_msg:
        if "invalid" in error_msg:
            return ErrorType.CONTRACT_VIOLATION

    # HTTP errors - classify by status code
    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        if 400 <= status_code < 500:
            # Client errors - check for specific patterns
            if status_code == 409:
                return ErrorType.CONFLICT
            if status_code == 422:
                return ErrorType.VALIDATION_FAILED
            if status_code == 408:
                return ErrorType.TIMEOUT
            # Other 4xx are usually permanent
            return ErrorType.PERMANENT
        elif 500 <= status_code < 600:
            # Server errors are transient
            return ErrorType.TRANSIENT

    # DNS/resolution errors
    if "dns" in error_msg or "resolve" in error_msg:
        return ErrorType.TRANSIENT

    # Resource exhaustion
    if "resource" in error_msg and "exhausted" in error_msg:
        return ErrorType.TRANSIENT
    if "busy" in error_msg or "too many" in error_msg:
        return ErrorType.TRANSIENT

    # Default to permanent for unknown errors
    logger.warning(f"Unknown error type classified as permanent: {type(exception).__name__}: {exception}")
    return ErrorType.PERMANENT


# ============================================================================
# Retry Calculation
# ============================================================================


@dataclass
class RetryDecision:
    """Decision about whether and when to retry."""

    should_retry: bool
    next_attempt: int
    delay_seconds: float
    next_retry_at: datetime | None = None
    reason: str = ""
    retry_exhausted: bool = False


def calculate_retry_decision(
    execution: TaskExecution,
    error_type: ErrorType,
    phase: RunnerPhase,
    retry_matrix: RetryMatrix | None = None,
) -> RetryDecision:
    """Calculate whether to retry and when.

    Per REQ-012-09: Keine Endlosschleifen: max_attempts, Backoff, next_retry_at.

    Args:
        execution: The TaskExecution with current attempt count
        error_type: Classified error type
        phase: Current runner phase
        retry_matrix: Retry matrix configuration

    Returns:
        RetryDecision with retry recommendation
    """
    retry_matrix = retry_matrix or DEFAULT_RETRY_MATRIX
    policy = retry_matrix.get_policy(phase)

    current_attempt = execution.attempt or 1
    max_attempts = execution.max_attempts or policy.max_attempts

    # Check if error is retryable
    if not error_type.is_retryable:
        return RetryDecision(
            should_retry=False,
            next_attempt=current_attempt,
            delay_seconds=0,
            reason=f"Error type {error_type.value} is not retryable",
            retry_exhausted=True,
        )

    # Check if max attempts exceeded
    if current_attempt >= max_attempts:
        return RetryDecision(
            should_retry=False,
            next_attempt=current_attempt,
            delay_seconds=0,
            reason=f"Max attempts ({max_attempts}) exhausted",
            retry_exhausted=True,
        )

    # Calculate backoff delay
    delay = min(
        policy.base_delay_seconds * (policy.backoff_multiplier ** (current_attempt - 1)),
        policy.max_delay_seconds,
    )

    # Add jitter (0-10% of delay)
    import random

    jitter = delay * policy.jitter_factor * (2 * random.random() - 1)
    delay += jitter
    delay = max(0, delay)  # Ensure non-negative

    next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)

    return RetryDecision(
        should_retry=True,
        next_attempt=current_attempt + 1,
        delay_seconds=delay,
        next_retry_at=next_retry_at,
        reason=f"Retry {current_attempt + 1}/{max_attempts} scheduled",
    )


# ============================================================================
# Stale Execution Detection
# ============================================================================


@dataclass
class StaleThresholds:
    """Thresholds for stale detection per phase."""

    # Heartbeat timeout (no heartbeat received)
    heartbeat_timeout_seconds: int = 300  # 5 minutes

    # Update timeout (no state change)
    update_timeout_seconds: int = 600  # 10 minutes

    # Max execution duration (absolute)
    max_duration_seconds: int = 3600  # 1 hour

    # Phase-specific overrides
    phase_timeouts: dict[RunnerPhase, int] = field(default_factory=dict)


DEFAULT_STALE_THRESHOLDS = StaleThresholds()


def is_execution_stale(
    execution: TaskExecution,
    thresholds: StaleThresholds | None = None,
    now: datetime | None = None,
) -> bool:
    """Check if an execution is stale.

    Per REQ-012-09: Stale Detection über heartbeat_at, updated_at, Phase und maximale Laufzeit.

    Args:
        execution: The TaskExecution to check
        thresholds: Stale detection thresholds
        now: Current time (defaults to now)

    Returns:
        True if execution is considered stale
    """
    thresholds = thresholds or DEFAULT_STALE_THRESHOLDS
    now = now or datetime.now(timezone.utc)

    if not execution.started_at:
        # Not started yet - check against queued time
        if execution.created_at:
            age = (now - execution.created_at).total_seconds()
            # If queued for too long without starting, consider stale
            if age > thresholds.update_timeout_seconds:
                return True
        return False

    # Check heartbeat timeout
    if execution.heartbeat_at:
        heartbeat_age = (now - execution.heartbeat_at).total_seconds()
        # Phase-specific heartbeat timeout
        phase_timeout = thresholds.phase_timeouts.get(
            RunnerPhase(execution.phase) if execution.phase else RunnerPhase.STREAM,
            thresholds.heartbeat_timeout_seconds,
        )
        if heartbeat_age > phase_timeout:
            logger.info(
                f"Execution {execution.id} stale: heartbeat timeout "
                f"({heartbeat_age:.0f}s > {phase_timeout}s)"
            )
            return True

    # Check update timeout
    update_age = (now - execution.updated_at).total_seconds()
    if update_age > thresholds.update_timeout_seconds:
        logger.info(
            f"Execution {execution.id} stale: update timeout "
            f"({update_age:.0f}s > {thresholds.update_timeout_seconds}s)"
        )
        return True

    # Check max duration
    execution_duration = (now - execution.started_at).total_seconds()
    max_duration = thresholds.phase_timeouts.get(
        RunnerPhase(execution.phase) if execution.phase else RunnerPhase.STREAM,
        thresholds.max_duration_seconds,
    )
    if execution_duration > max_duration:
        logger.info(
            f"Execution {execution.id} stale: max duration exceeded "
            f"({execution_duration:.0f}s > {max_duration}s)"
        )
        return True

    return False


def find_stale_executions(
    session: Session,
    thresholds: StaleThresholds | None = None,
    statuses: list[str] | None = None,
) -> list[TaskExecution]:
    """Find all stale executions in the database.

    Per REQ-012-09: Stale Query für alte Executions.

    Args:
        session: Database session
        thresholds: Stale detection thresholds
        statuses: Filter by specific statuses (defaults to active states)

    Returns:
        List of stale TaskExecution objects
    """
    thresholds = thresholds or DEFAULT_STALE_THRESHOLDS
    now = datetime.now(timezone.utc)

    # Default to active statuses (not in final state)
    if statuses is None:
        statuses = [
            ExecutionStatus.QUEUED.value,
            ExecutionStatus.DISPATCHING.value,
            ExecutionStatus.IN_PROGRESS.value,
            ExecutionStatus.RESULT_INSPECTION.value,
            ExecutionStatus.ADOPTING_COMMIT.value,
        ]

    # Build query with multiple stale conditions
    conditions = []

    # Heartbeat timeout
    heartbeat_cutoff = now - timedelta(seconds=thresholds.heartbeat_timeout_seconds)
    conditions.append(
        and_(
            TaskExecution.heartbeat_at <= heartbeat_cutoff,
            TaskExecution.heartbeat_at.isnot(None),
            TaskExecution.status.in_(statuses),
        )
    )

    # Update timeout
    update_cutoff = now - timedelta(seconds=thresholds.update_timeout_seconds)
    conditions.append(
        and_(
            TaskExecution.updated_at <= update_cutoff,
            TaskExecution.status.in_(statuses),
        )
    )

    # Max duration
    duration_cutoff = now - timedelta(seconds=thresholds.max_duration_seconds)
    conditions.append(
        and_(
            TaskExecution.started_at <= duration_cutoff,
            TaskExecution.status.in_(statuses),
        )
    )

    # Combine conditions
    query = session.query(TaskExecution).filter(or_(*conditions))

    stale_executions = query.all()
    logger.info(f"Found {len(stale_executions)} stale executions")

    return stale_executions


# ============================================================================
# Custom Exception Types
# ============================================================================


class ConflictError(Exception):
    """Raised when a conflict is detected (Git, state, etc.)."""

    def __init__(self, message: str, details: dict | None = None):
        self.details = details or {}
        super().__init__(message)


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message)


class ContractViolationError(Exception):
    """Raised when a protocol/API contract is violated."""

    def __init__(self, message: str, expected: Any = None, actual: Any = None):
        self.expected = expected
        self.actual = actual
        super().__init__(message)


# ============================================================================
# Recovery Actions
# ============================================================================


class RecoveryAction(str, Enum):
    """Actions to take during recovery."""

    OBSERVE = "observe"  # Continue observing, no action
    RETRY = "retry"  # Schedule retry
    REVIEW = "review"  # Mark for manual review
    FAILED = "failed"  # Mark as permanently failed
    REVALIDATE_ADOPTION = "revalidate_adoption"  # Re-validate Git adoption


@dataclass
class RecoveryDecision:
    """Decision about recovery action."""

    action: RecoveryAction
    reason: str
    error_type: ErrorType
    phase: RunnerPhase
    should_update_status: bool = False
    new_status: ExecutionStatus | None = None
    next_retry_at: datetime | None = None
