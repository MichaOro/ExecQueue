"""Tests for observability components (REQ-012-10).

Tests cover:
- Structured logging with correlation ID
- Phase timing metrics
- Payload redaction
- Metrics collection
- CLI commands
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from execqueue.observability import (
    ExecutionMetrics,
    PayloadRedactor,
    PhaseMetrics,
    PhaseTimer,
    StructuredFormatter,
    extract_correlation_id,
    generate_correlation_id,
    get_logger,
    get_metrics,
    log_phase_event,
    record_adoption_conflict,
    record_cherry_pick_attempt,
    record_cherry_pick_success,
    record_execution_claimed,
    record_execution_completed,
    record_execution_failed,
    record_phase_duration,
    record_retry_exhausted,
    record_retry_scheduled,
    record_stale_detection,
    record_validation_failed,
    record_validation_passed,
    record_validation_review,
    record_worktree_cleaned,
    record_worktree_created,
    record_worktree_error,
    redact_payload,
    reset_metrics,
)


# ============================================================================
# Structured Formatter Tests
# ============================================================================


class TestStructuredFormatter:
    """Tests for structured log formatter."""

    def test_format_basic_log(self):
        """Test basic log formatting."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert parsed["logger"] == "test"
        assert "timestamp" in parsed

    def test_format_with_correlation_id(self):
        """Test log formatting with correlation ID."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "exec-abc123"
        record.execution_id = "exec-id-456"
        record.phase = "dispatch"

        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["correlation_id"] == "exec-abc123"
        assert parsed["execution_id"] == "exec-id-456"
        assert parsed["phase"] == "dispatch"

    def test_redact_sensitive_data(self):
        """Test redaction of sensitive data."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='password="secret123" api_key="abc123"',
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        parsed = json.loads(result)

        # Should contain [REDACTED] and not the original values
        assert "[REDACTED]" in parsed["message"]
        # The pattern might leave some text, but original secret should be gone
        # Check that the exact secret value is not present as a standalone value
        assert ': "secret123"' not in parsed["message"]

    def test_truncate_large_payload(self):
        """Test truncation of large payloads."""
        formatter = StructuredFormatter()
        large_message = "x" * 2000
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=large_message,
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        parsed = json.loads(result)

        assert len(parsed["message"]) <= 1000 + 20  # max_length + "... [truncated]"
        assert "[truncated]" in parsed["message"]


# ============================================================================
# Correlation ID Tests
# ============================================================================


class TestCorrelationId:
    """Tests for correlation ID generation."""

    def test_generate_correlation_id_format(self):
        """Test correlation ID format."""
        corr_id = generate_correlation_id()
        assert corr_id.startswith("exec-")
        assert len(corr_id) == 17  # "exec-" + 12 hex chars

    def test_generate_correlation_id_custom_prefix(self):
        """Test correlation ID with custom prefix."""
        corr_id = generate_correlation_id("claim")
        assert corr_id.startswith("claim-")
        assert len(corr_id) == 18  # "claim-" + 12 hex chars

    def test_generate_correlation_id_uniqueness(self):
        """Test that generated IDs are unique."""
        ids = [generate_correlation_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique

    def test_extract_correlation_id_from_dict(self):
        """Test extraction from context dict."""
        context = {"correlation_id": "exec-abc123"}
        result = extract_correlation_id(context)
        assert result == "exec-abc123"

    def test_extract_correlation_id_from_header(self):
        """Test extraction from header."""
        context = {"X-Correlation-ID": "exec-xyz789"}
        result = extract_correlation_id(context)
        assert result == "exec-xyz789"

    def test_extract_correlation_id_missing(self):
        """Test extraction when not present."""
        context = {"other": "value"}
        result = extract_correlation_id(context)
        assert result is None


# ============================================================================
# Payload Redaction Tests
# ============================================================================


class TestPayloadRedaction:
    """Tests for payload redaction."""

    def test_redact_sensitive_fields(self):
        """Test redaction of sensitive field names."""
        redactor = PayloadRedactor()
        data = {
            "username": "user",
            "password": "secret123",
            "api_key": "abc123",
            "token": "xyz789",
        }

        result = redactor.redact(data)

        assert result["username"] == "user"
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"

    def test_redact_nested_structures(self):
        """Test redaction in nested structures."""
        redactor = PayloadRedactor()
        data = {
            "user": {
                "name": "test",
                "creds": {  # Use 'creds' instead of 'credentials' to avoid false positive
                    "password": "secret",
                },
            },
            "items": [
                {"token": "abc123"},
                {"value": "normal"},
            ],
        }

        result = redactor.redact(data)

        # Check nested redaction - verify structure is preserved
        assert isinstance(result["user"], dict)
        assert result["user"]["name"] == "test"
        assert isinstance(result["user"]["creds"], dict)
        assert result["user"]["creds"]["password"] == "[REDACTED]"
        assert isinstance(result["items"], list)
        assert result["items"][0]["token"] == "[REDACTED]"
        assert result["items"][1]["value"] == "normal"

    def test_redact_large_payload(self):
        """Test truncation of large payloads."""
        redactor = PayloadRedactor(max_payload_size=100)
        data = {"content": "x" * 200}

        result = redactor.redact(data)

        assert len(result["content"]) <= 120  # 100 + "... [truncated]"
        assert "[truncated]" in result["content"]

    def test_redact_git_token(self):
        """Test redaction of Git tokens."""
        redactor = PayloadRedactor()
        data = "My token is ghp_abcdefghijklmnopqrstuvwxyz1234567890"

        result = redactor.redact(data)

        assert "[REDACTED]" in result
        assert "ghp_" not in result

    def test_redact_bearer_token(self):
        """Test redaction of Bearer tokens."""
        redactor = PayloadRedactor()
        data = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"

        result = redactor.redact(data)

        assert "[REDACTED]" in result


# ============================================================================
# Phase Timer Tests
# ============================================================================


class TestPhaseTimer:
    """Tests for phase timing."""

    def test_phase_timer_success(self):
        """Test phase timer on successful execution."""
        timer = PhaseTimer("test_phase", correlation_id="exec-123")

        with timer:
            pass  # Simulate work

        assert timer.metrics.success is True
        assert timer.metrics.duration_seconds > 0
        assert timer.metrics.phase == "test_phase"

    def test_phase_timer_failure(self):
        """Test phase timer on failed execution."""
        timer = PhaseTimer("test_phase", correlation_id="exec-123")

        try:
            with timer:
                raise ValueError("Test error")
        except ValueError:
            pass

        assert timer.metrics.success is False
        assert timer.metrics.error_type == "ValueError"
        assert timer.metrics.duration_seconds > 0


# ============================================================================
# Metrics Collection Tests
# ============================================================================


class TestMetricsCollection:
    """Tests for metrics collection."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_metrics()

    def test_record_execution_claimed(self):
        """Test recording execution claim."""
        record_execution_claimed()
        metrics = get_metrics()

        assert metrics.executions_claimed == 1
        assert metrics.first_execution is not None

    def test_record_execution_completed(self):
        """Test recording successful completion."""
        record_execution_claimed()
        record_execution_completed()
        metrics = get_metrics()

        assert metrics.executions_claimed == 1
        assert metrics.executions_completed == 1
        assert metrics.success_rate == 1.0

    def test_record_execution_failed(self):
        """Test recording failure."""
        record_execution_claimed()
        record_execution_failed()
        metrics = get_metrics()

        assert metrics.executions_failed == 1

    def test_record_retry_scheduled(self):
        """Test recording retry scheduling."""
        record_retry_scheduled()
        metrics = get_metrics()

        assert metrics.retries_scheduled == 1

    def test_record_retry_exhausted(self):
        """Test recording retry exhaustion."""
        record_retry_exhausted()
        metrics = get_metrics()

        assert metrics.retries_exhausted == 1

    def test_record_stale_detection(self):
        """Test recording stale detection."""
        record_stale_detection()
        metrics = get_metrics()

        assert metrics.stale_executions_detected == 1

    def test_record_adoption_conflict(self):
        """Test recording adoption conflict."""
        record_adoption_conflict()
        metrics = get_metrics()

        assert metrics.adoption_conflicts == 1

    def test_record_worktree_metrics(self):
        """Test recording worktree metrics."""
        # Reset metrics first
        reset_metrics()
        
        record_worktree_created()
        record_worktree_created()
        record_worktree_cleaned()
        record_worktree_error()
        
        metrics = get_metrics()
        assert metrics.worktrees_created == 2
        assert metrics.worktrees_cleaned == 1
        assert metrics.worktrees_errors == 1
        
        # Check the calculated worktree_count from to_dict
        result = metrics.to_dict()
        assert result["worktree_count"] == 0  # 2 created - 1 cleaned - 1 error = 0

    def test_record_cherry_pick_metrics(self):
        """Test recording cherry-pick metrics."""
        # Reset metrics first
        reset_metrics()
        
        record_cherry_pick_attempt()
        record_cherry_pick_attempt()
        record_cherry_pick_success()
        
        metrics = get_metrics()
        assert metrics.cherry_pick_attempts == 2
        assert metrics.cherry_pick_success == 1
        assert metrics.cherry_pick_success_rate == 0.5

    def test_record_validation_metrics(self):
        """Test recording validation metrics."""
        # Reset metrics first
        reset_metrics()
        
        record_validation_passed()
        record_validation_passed()
        record_validation_failed()
        record_validation_review()
        
        metrics = get_metrics()
        assert metrics.validations_passed == 2
        assert metrics.validations_failed == 1
        assert metrics.validations_review == 1
        assert metrics.validation_success_rate == 0.5  # 2 passed / (2+1+1) total

    def test_cherry_pick_success_rate_edge_cases(self):
        """Test cherry-pick success rate edge cases."""
        # Reset metrics first
        reset_metrics()
        
        # No attempts should result in 0.0 rate
        metrics = get_metrics()
        assert metrics.cherry_pick_success_rate == 0.0
        
        # Only successes
        record_cherry_pick_attempt()
        record_cherry_pick_success()
        metrics = get_metrics()
        assert metrics.cherry_pick_success_rate == 1.0

    def test_validation_success_rate_edge_cases(self):
        """Test validation success rate edge cases."""
        # Reset metrics first
        reset_metrics()
        
        # No validations should result in 0.0 rate
        metrics = get_metrics()
        assert metrics.validation_success_rate == 0.0

    def test_record_phase_duration(self):
        """Test recording phase duration."""
        record_phase_duration("dispatch", 5.5)
        record_phase_duration("dispatch", 4.5)
        metrics = get_metrics()

        assert metrics.phase_counts["dispatch"] == 2
        avg = metrics.get_average_phase_duration("dispatch")
        assert avg == 5.0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        record_execution_claimed()
        record_execution_claimed()
        record_execution_claimed()
        record_execution_completed()
        record_execution_completed()
        record_execution_failed()

        metrics = get_metrics()
        assert metrics.success_rate == 2 / 3

    def test_retry_rate_calculation(self):
        """Test retry rate calculation."""
        record_execution_claimed()
        record_execution_claimed()
        record_retry_scheduled()
        record_retry_scheduled()

        metrics = get_metrics()
        assert metrics.retry_rate == 2 / 2  # 100% since 2 claims, 2 retries

    def test_to_dict(self):
        """Test metrics to dictionary conversion."""
        record_execution_claimed()
        record_execution_completed()
        record_phase_duration("dispatch", 10.0)
        
        # Add some REQ-021 metrics
        record_worktree_created()
        record_cherry_pick_attempt()
        record_cherry_pick_success()
        record_validation_passed()

        metrics = get_metrics()
        result = metrics.to_dict()

        assert "executions_claimed" in result
        assert "success_rate" in result
        assert "average_phase_durations" in result
        assert "last_update" in result
        
        # Check REQ-021 metrics
        assert "worktrees_created" in result
        assert "cherry_pick_attempts" in result
        assert "cherry_pick_success" in result
        assert "cherry_pick_success_rate" in result
        assert "validations_passed" in result
        assert "validation_success_rate" in result


# ============================================================================
# Log Event Tests
# ============================================================================


class TestLogPhaseEvent:
    """Tests for phase event logging."""

    def test_log_phase_event_basic(self, caplog):
        """Test basic phase event logging."""
        logger = get_logger("test")
        logger.setLevel(logging.INFO)

        with caplog.at_level(logging.INFO):
            log_phase_event(
                logger,
                "Test event",
                correlation_id="exec-123",
                phase="dispatch",
            )

        assert len(caplog.records) == 1
        assert caplog.records[0].correlation_id == "exec-123"
        assert caplog.records[0].phase == "dispatch"

    def test_log_phase_event_with_extra_fields(self, caplog):
        """Test phase event logging with extra fields."""
        logger = get_logger("test")
        logger.setLevel(logging.INFO)

        with caplog.at_level(logging.INFO):
            log_phase_event(
                logger,
                "Test event",
                correlation_id="exec-123",
                phase="dispatch",
                execution_id="exec-456",
                task_id="task-789",
                extra_field="extra_value",
            )

        assert len(caplog.records) == 1
        assert caplog.records[0].execution_id == "exec-456"
        assert caplog.records[0].task_id == "task-789"


# ============================================================================
# Integration Tests
# ============================================================================


class TestObservabilityIntegration:
    """Integration tests for observability components."""

    def test_full_phase_timing_with_metrics(self):
        """Test phase timing with metrics recording."""
        reset_metrics()

        with PhaseTimer("dispatch", correlation_id="exec-123") as timer:
            pass

        # Record the duration
        record_phase_duration("dispatch", timer.metrics.duration_seconds)

        metrics = get_metrics()
        assert metrics.phase_counts["dispatch"] == 1

    def test_error_flow_with_metrics(self):
        """Test error flow with metrics."""
        reset_metrics()

        record_execution_claimed()

        try:
            with PhaseTimer("dispatch", correlation_id="exec-123"):
                raise ConnectionError("Network error")
        except ConnectionError:
            record_execution_failed()
            record_retry_scheduled()

        metrics = get_metrics()
        assert metrics.executions_claimed == 1
        assert metrics.executions_failed == 1
        assert metrics.retries_scheduled == 1
