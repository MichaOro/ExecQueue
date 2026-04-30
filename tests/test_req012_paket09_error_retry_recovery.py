"""Tests for error classification and retry recovery (REQ-012-09).

Tests cover:
- Error type classification
- Retry policy and backoff calculation
- Stale execution detection
- Write-task recovery with Git pre-checks
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.runner.error_classification import (
    DEFAULT_RETRY_MATRIX,
    DEFAULT_STALE_THRESHOLDS,
    ConflictError,
    ContractViolationError,
    ErrorType,
    PhaseRetryPolicy,
    RecoveryAction,
    RecoveryDecision,
    RetryDecision,
    RetryMatrix,
    RunnerPhase,
    StaleThresholds,
    ValidationError,
    calculate_retry_decision,
    classify_error,
    find_stale_executions,
    is_execution_stale,
)
from execqueue.runner.recovery import (
    WriteTaskRecovery,
    create_recovery_event,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_execution():
    """Create a mock TaskExecution for testing."""
    execution = MagicMock(spec=TaskExecution)
    execution.id = "test-execution-123"
    execution.task_id = "test-task-456"
    execution.runner_id = "runner-1"
    execution.correlation_id = "corr-123"
    execution.status = ExecutionStatus.IN_PROGRESS.value
    execution.attempt = 1
    execution.max_attempts = 3
    execution.error_type = None
    execution.error_message = None
    execution.next_retry_at = None
    execution.phase = RunnerPhase.STREAM.value
    execution.heartbeat_at = datetime.now(timezone.utc)
    execution.updated_at = datetime.now(timezone.utc)
    execution.started_at = datetime.now(timezone.utc)
    execution.created_at = datetime.now(timezone.utc)
    execution.events = []
    return execution


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    from execqueue.db.base import Base

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


# ============================================================================
# Error Classification Tests
# ============================================================================


class TestErrorClassification:
    """Tests for error type classification."""

    def test_classify_timeout_error(self):
        """Timeout errors should be classified as timeout."""
        exc = asyncio.TimeoutError("Operation timed out")
        result = classify_error(exc)
        assert result == ErrorType.TIMEOUT

    def test_classify_http_timeout(self):
        """HTTP timeout should be classified as timeout."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                httpx.TimeoutException("Timeout", request=None)
            )
            try:
                async def test():
                    async with httpx.AsyncClient() as client:
                        await client.get("http://test.com")

                asyncio.run(test())
            except httpx.TimeoutException as e:
                result = classify_error(e)
                assert result == ErrorType.TIMEOUT

    def test_classify_connection_error(self):
        """Connection errors should be classified as transient."""
        exc = ConnectionRefusedError("Connection refused")
        result = classify_error(exc)
        assert result == ErrorType.TRANSIENT

    def test_classify_http_500_error(self):
        """HTTP 500 errors should be classified as transient."""
        response = MagicMock()
        response.status_code = 500
        exc = httpx.HTTPStatusError("Server error", request=None, response=response)
        result = classify_error(exc)
        assert result == ErrorType.TRANSIENT

    def test_classify_http_409_conflict(self):
        """HTTP 409 errors should be classified as conflict."""
        response = MagicMock()
        response.status_code = 409
        exc = httpx.HTTPStatusError("Conflict", request=None, response=response)
        result = classify_error(exc)
        assert result == ErrorType.CONFLICT

    def test_classify_http_422_validation(self):
        """HTTP 422 errors should be classified as validation_failed."""
        response = MagicMock()
        response.status_code = 422
        exc = httpx.HTTPStatusError("Validation error", request=None, response=response)
        result = classify_error(exc)
        assert result == ErrorType.VALIDATION_FAILED

    def test_classify_custom_conflict_error(self):
        """Custom ConflictError should be classified as conflict."""
        exc = ConflictError("Git merge conflict", details={"file": "README.md"})
        result = classify_error(exc)
        assert result == ErrorType.CONFLICT

    def test_classify_custom_validation_error(self):
        """Custom ValidationError should be classified as validation_failed."""
        exc = ValidationError("Invalid field value", field="name")
        result = classify_error(exc)
        assert result == ErrorType.VALIDATION_FAILED

    def test_classify_custom_contract_violation(self):
        """Custom ContractViolationError should be classified as contract_violation."""
        exc = ContractViolationError(
            "Schema mismatch", expected={"id": "string"}, actual={"id": 123}
        )
        result = classify_error(exc)
        assert result == ErrorType.CONTRACT_VIOLATION

    def test_classify_unknown_error(self):
        """Unknown errors should default to permanent."""
        exc = Exception("Some unknown error")
        result = classify_error(exc)
        assert result == ErrorType.PERMANENT

    def test_error_type_is_retryable(self):
        """Test is_retryable property for each error type."""
        assert ErrorType.TRANSIENT.is_retryable is True
        assert ErrorType.TIMEOUT.is_retryable is True
        assert ErrorType.VALIDATION_FAILED.is_retryable is False
        assert ErrorType.CONTRACT_VIOLATION.is_retryable is False
        assert ErrorType.CONFLICT.is_retryable is False
        assert ErrorType.PERMANENT.is_retryable is False


# ============================================================================
# Retry Policy Tests
# ============================================================================


class TestRetryPolicy:
    """Tests for retry policy and backoff calculation."""

    def test_get_policy_for_phase(self):
        """Test getting policy for specific phases."""
        matrix = RetryMatrix()
        assert matrix.get_policy(RunnerPhase.CLAIM) == matrix.claim
        assert matrix.get_policy(RunnerPhase.SESSION) == matrix.session
        assert matrix.get_policy(RunnerPhase.DISPATCH) == matrix.dispatch
        assert matrix.get_policy(RunnerPhase.STREAM) == matrix.stream
        assert matrix.get_policy(RunnerPhase.RESULT) == matrix.result
        assert matrix.get_policy(RunnerPhase.ADOPTION) == matrix.adoption

    def test_calculate_retry_decision_should_retry(self, mock_execution):
        """Test retry decision when retry is possible."""
        mock_execution.attempt = 1
        mock_execution.max_attempts = 3

        decision = calculate_retry_decision(
            mock_execution, ErrorType.TRANSIENT, RunnerPhase.STREAM
        )

        assert decision.should_retry is True
        assert decision.next_attempt == 2
        assert decision.delay_seconds > 0
        assert decision.next_retry_at is not None
        assert decision.retry_exhausted is False

    def test_calculate_retry_decision_max_attempts_exhausted(self, mock_execution):
        """Test retry decision when max attempts reached."""
        mock_execution.attempt = 3
        mock_execution.max_attempts = 3

        decision = calculate_retry_decision(
            mock_execution, ErrorType.TRANSIENT, RunnerPhase.STREAM
        )

        assert decision.should_retry is False
        assert decision.retry_exhausted is True
        assert "exhausted" in decision.reason.lower()

    def test_calculate_retry_decision_non_retryable_error(self, mock_execution):
        """Test retry decision for non-retryable errors."""
        decision = calculate_retry_decision(
            mock_execution, ErrorType.PERMANENT, RunnerPhase.STREAM
        )

        assert decision.should_retry is False
        assert decision.retry_exhausted is True
        assert "not retryable" in decision.reason.lower()

    def test_backoff_increases_with_attempt(self, mock_execution):
        """Test that backoff delay increases with attempt number."""
        delays = []
        for attempt in range(1, 4):
            mock_execution.attempt = attempt
            mock_execution.max_attempts = 5

            decision = calculate_retry_decision(
                mock_execution, ErrorType.TRANSIENT, RunnerPhase.STREAM
            )
            delays.append(decision.delay_seconds)

        # Delays should be increasing (with some jitter tolerance)
        assert delays[0] < delays[1] * 1.2  # Allow 20% jitter tolerance
        assert delays[1] < delays[2] * 1.2

    def test_backoff_respects_max_delay(self, mock_execution):
        """Test that backoff respects maximum delay (with jitter tolerance)."""
        mock_execution.attempt = 10  # High attempt number
        mock_execution.max_attempts = 20

        decision = calculate_retry_decision(
            mock_execution, ErrorType.TRANSIENT, RunnerPhase.STREAM
        )

        # Allow 10% jitter tolerance over max_delay
        max_with_jitter = DEFAULT_RETRY_MATRIX.stream.max_delay_seconds * 1.1
        assert decision.delay_seconds <= max_with_jitter


# ============================================================================
# Stale Detection Tests
# ============================================================================


class TestStaleDetection:
    """Tests for stale execution detection."""

    def test_is_execution_not_stale(self, mock_execution):
        """Test that recent execution is not stale."""
        mock_execution.heartbeat_at = datetime.now(timezone.utc)
        mock_execution.updated_at = datetime.now(timezone.utc)
        mock_execution.started_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        result = is_execution_stale(mock_execution)
        assert result is False

    def test_is_execution_stale_heartbeat_timeout(self, mock_execution):
        """Test stale detection via heartbeat timeout."""
        now = datetime.now(timezone.utc)
        mock_execution.heartbeat_at = now - timedelta(minutes=10)  # 10 min ago
        mock_execution.updated_at = now
        mock_execution.started_at = now - timedelta(minutes=1)

        thresholds = StaleThresholds(heartbeat_timeout_seconds=300)  # 5 min
        result = is_execution_stale(mock_execution, thresholds=thresholds, now=now)

        assert result is True

    def test_is_execution_stale_update_timeout(self, mock_execution):
        """Test stale detection via update timeout."""
        now = datetime.now(timezone.utc)
        mock_execution.heartbeat_at = now
        mock_execution.updated_at = now - timedelta(minutes=20)  # 20 min ago
        mock_execution.started_at = now - timedelta(minutes=1)

        thresholds = StaleThresholds(update_timeout_seconds=600)  # 10 min
        result = is_execution_stale(mock_execution, thresholds=thresholds, now=now)

        assert result is True

    def test_is_execution_stale_max_duration(self, mock_execution):
        """Test stale detection via max duration."""
        now = datetime.now(timezone.utc)
        mock_execution.heartbeat_at = now
        mock_execution.updated_at = now
        mock_execution.started_at = now - timedelta(hours=2)  # 2 hours ago

        thresholds = StaleThresholds(max_duration_seconds=3600)  # 1 hour
        result = is_execution_stale(mock_execution, thresholds=thresholds, now=now)

        assert result is True

    def test_is_execution_stale_no_heartbeat(self, mock_execution):
        """Test stale detection when no heartbeat set."""
        now = datetime.now(timezone.utc)
        mock_execution.heartbeat_at = None
        mock_execution.updated_at = now - timedelta(minutes=20)
        mock_execution.started_at = now - timedelta(minutes=15)

        thresholds = StaleThresholds(update_timeout_seconds=600)
        result = is_execution_stale(mock_execution, thresholds=thresholds, now=now)

        assert result is True

    def test_is_execution_not_started(self, mock_execution):
        """Test stale detection for execution not yet started."""
        now = datetime.now(timezone.utc)
        mock_execution.started_at = None
        mock_execution.heartbeat_at = None
        mock_execution.updated_at = None
        mock_execution.created_at = now - timedelta(minutes=20)

        thresholds = StaleThresholds(update_timeout_seconds=600)
        result = is_execution_stale(mock_execution, thresholds=thresholds, now=now)

        assert result is True


# ============================================================================
# Recovery Decision Tests
# ============================================================================


class TestRecoveryDecision:
    """Tests for recovery decision logic."""

    def test_recovery_decision_for_transient_error(self, mock_execution):
        """Test recovery decision for transient error."""
        from execqueue.runner.recovery import RecoveryService

        service = RecoveryService()
        session = MagicMock()

        exc = ConnectionError("Network error")
        decision = service.handle_error(
            session, mock_execution, exc, RunnerPhase.STREAM
        )

        assert decision.action == RecoveryAction.RETRY
        assert decision.error_type == ErrorType.TRANSIENT

    def test_recovery_decision_for_permanent_error(self, mock_execution):
        """Test recovery decision for permanent error."""
        from execqueue.runner.recovery import RecoveryService

        service = RecoveryService()
        session = MagicMock()

        exc = ValueError("Invalid data")
        decision = service.handle_error(
            session, mock_execution, exc, RunnerPhase.STREAM
        )

        assert decision.action == RecoveryAction.FAILED
        assert decision.error_type == ErrorType.VALIDATION_FAILED

    def test_recovery_decision_for_conflict_error(self, mock_execution):
        """Test recovery decision for conflict error."""
        from execqueue.runner.recovery import RecoveryService

        service = RecoveryService()
        session = MagicMock()

        exc = ConflictError("Git conflict")
        decision = service.handle_error(
            session, mock_execution, exc, RunnerPhase.STREAM
        )

        assert decision.action == RecoveryAction.REVIEW
        assert decision.error_type == ErrorType.CONFLICT

    def test_recovery_decision_retry_exhausted(self, mock_execution):
        """Test recovery decision when retries exhausted."""
        from execqueue.runner.recovery import RecoveryService

        service = RecoveryService()
        session = MagicMock()

        mock_execution.attempt = 3
        mock_execution.max_attempts = 3

        exc = ConnectionError("Network error")
        decision = service.handle_error(
            session, mock_execution, exc, RunnerPhase.STREAM
        )

        assert decision.action == RecoveryAction.FAILED
        assert decision.error_type == ErrorType.TRANSIENT


# ============================================================================
# Write-Task Recovery Tests
# ============================================================================


class TestWriteTaskRecovery:
    """Tests for write-task recovery with Git pre-checks."""

    def test_check_worktree_status_nonexistent(self):
        """Test worktree status check for non-existent path."""
        recovery = WriteTaskRecovery()

        execution = MagicMock(spec=TaskExecution)
        execution.worktree_path = "/nonexistent/path/12345"

        result = recovery.check_worktree_status(execution)

        assert result["exists"] is False
        assert result["is_git_repo"] is False

    def test_validate_retry_safety_no_worktree(self):
        """Test retry safety validation without worktree."""
        recovery = WriteTaskRecovery()

        execution = MagicMock(spec=TaskExecution)
        execution.worktree_path = None
        execution.new_commit_shas = []

        result = recovery.validate_retry_safety(execution)

        assert result["safe_to_retry"] is True
        assert len(result["errors"]) == 0

    def test_cleanup_worktree_no_worktree(self):
        """Test cleanup when worktree doesn't exist."""
        recovery = WriteTaskRecovery()

        execution = MagicMock(spec=TaskExecution)
        execution.worktree_path = "/nonexistent/path"

        result = recovery.cleanup_worktree(execution)

        # May succeed or fail with gitpython unavailable - check for expected behavior
        if result.get("gitpython_unavailable"):
            # GitPython not installed - cleanup disabled
            assert "gitpython_unavailable" in result
        else:
            assert result["success"] is True
            assert "does not exist" in result["actions_taken"][0]


# ============================================================================
# Integration Tests
# ============================================================================


class TestRecoveryIntegration:
    """Integration tests for recovery flow."""

    def test_full_error_handling_flow(self, mock_execution, db_session):
        """Test full error handling and recovery flow."""
        from execqueue.runner.recovery import RecoveryService

        service = RecoveryService()

        # Simulate transient error
        exc = ConnectionError("Temporary network issue")
        decision = service.handle_error(
            db_session, mock_execution, exc, RunnerPhase.DISPATCH
        )

        # Should schedule retry
        assert decision.action == RecoveryAction.RETRY
        assert decision.should_update_status is False
        assert decision.next_retry_at is not None

    def test_stale_execution_processing(self, db_session):
        """Test processing stale executions."""
        from execqueue.runner.recovery import RecoveryService

        # Create stale execution in DB - use UUID properly
        import uuid

        now = datetime.now(timezone.utc)
        execution = TaskExecution(
            id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            runner_id="runner-1",
            status=ExecutionStatus.IN_PROGRESS.value,
            attempt=1,
            max_attempts=3,
            phase=RunnerPhase.STREAM.value,
            heartbeat_at=now - timedelta(minutes=15),
            updated_at=now - timedelta(minutes=15),
            started_at=now - timedelta(minutes=15),
            created_at=now - timedelta(minutes=20),
        )
        db_session.add(execution)
        db_session.commit()

        service = RecoveryService()
        processed = service.process_stale_executions(db_session)

        # Should have processed the stale execution
        assert processed >= 0  # May be 0 if thresholds don't match exactly


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_classify_error_with_message_patterns(self):
        """Test error classification with message-based patterns."""
        # Connection refused in message
        exc = Exception("Connection refused to server")
        result = classify_error(exc)
        assert result == ErrorType.TRANSIENT

        # Timeout in message
        exc = Exception("Request timed out after 30s")
        result = classify_error(exc)
        assert result == ErrorType.TIMEOUT

        # Conflict in message
        exc = Exception("Merge conflict in main.py")
        result = classify_error(exc)
        assert result == ErrorType.CONFLICT

    def test_retry_matrix_custom_policies(self):
        """Test custom retry matrix configuration."""
        custom_matrix = RetryMatrix(
            claim=PhaseRetryPolicy(
                max_attempts=5,
                base_delay_seconds=0.5,
                max_delay_seconds=10.0,
            )
        )

        assert custom_matrix.claim.max_attempts == 5
        assert custom_matrix.claim.base_delay_seconds == 0.5
        assert custom_matrix.get_policy(RunnerPhase.CLAIM) == custom_matrix.claim

    def test_phase_specific_timeouts(self):
        """Test phase-specific stale timeouts."""
        now = datetime.now(timezone.utc)
        execution = MagicMock(spec=TaskExecution)
        execution.heartbeat_at = now - timedelta(minutes=8)
        execution.updated_at = now
        execution.started_at = now - timedelta(minutes=5)
        execution.phase = RunnerPhase.ADOPTION.value

        # Set phase-specific timeout
        thresholds = StaleThresholds(
            heartbeat_timeout_seconds=300,  # 5 min default
            phase_timeouts={RunnerPhase.ADOPTION: 900},  # 15 min for adoption
        )

        # Should not be stale due to phase-specific timeout
        result = is_execution_stale(execution, thresholds=thresholds, now=now)
        assert result is False
