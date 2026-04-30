"""Structured logging and observability for ExecQueue.

This module provides:
- Structured JSON logging with correlation ID propagation
- Phase timing metrics and instrumentation
- Payload redaction for sensitive data
- Basic metrics collection (counters, histograms)
"""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generator


class RunnerPhase(str, Enum):
    """Runner execution phases for observability."""

    CLAIM = "claim"
    SESSION = "session"
    DISPATCH = "dispatch"
    STREAM = "stream"
    RESULT = "result"
    ADOPTION = "adoption"


# ============================================================================
# Structured Logging
# ============================================================================


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter with correlation ID support.

    Per REQ-012-10: Strukturierte Logs mit Phase, Task-ID, Execution-ID,
    Runner-ID, Session-ID, Statuswechsel.
    """

    def __init__(
        self,
        include_fields: list[str] | None = None,
        redact_patterns: list[str] | None = None,
    ):
        """Initialize structured formatter.

        Args:
            include_fields: Additional fields to include in log output
            redact_patterns: Regex patterns for sensitive data redaction
        """
        super().__init__()
        self.include_fields = include_fields or []
        self.redact_patterns = redact_patterns or [
            r"password[\"']?\s*[:=]\s*[\"']?[^\"'\s]+",
            r"api[_-]?key[\"']?\s*[:=]\s*[\"']?[^\"'\s]+",
            r"token[\"']?\s*[:=]\s*[\"']?[^\"'\s]+",
            r"secret[\"']?\s*[:=]\s*[\"']?[^\"'\s]+",
        ]
        patterns_to_use = redact_patterns if redact_patterns is not None else self.redact_patterns
        self._redact_regex = re.compile(
            "|".join(f"({pattern})" for pattern in patterns_to_use),
            re.IGNORECASE,
        )

    def redact_sensitive(self, text: str) -> str:
        """Redact sensitive data from text.

        Per REQ-012-10: Keine großen/sensiblen Payloads landen ungeprüft in Logs.

        Args:
            text: Text to redact

        Returns:
            Text with sensitive data replaced with [REDACTED]
        """
        return self._redact_regex.sub(r"\1: [REDACTED]", text)

    def truncate_payload(self, value: Any, max_length: int = 1000) -> Any:
        """Truncate large payloads in log output.

        Args:
            value: Value to potentially truncate
            max_length: Maximum length for string values

        Returns:
            Truncated value if applicable
        """
        if isinstance(value, str) and len(value) > max_length:
            return value[:max_length] + "... [truncated]"
        return value

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON string with structured log data
        """
        # Extract structured fields from record
        extra_fields = {}
        for field_name in self.include_fields:
            if hasattr(record, field_name):
                extra_fields[field_name] = getattr(record, field_name)

        # Build structured log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self.redact_sensitive(record.getMessage()),
            "correlation_id": getattr(record, "correlation_id", None),
            "execution_id": getattr(record, "execution_id", None),
            "task_id": getattr(record, "task_id", None),
            "runner_id": getattr(record, "runner_id", None),
            "phase": getattr(record, "phase", None),
            "session_id": getattr(record, "session_id", None),
        }

        # Add extra fields
        log_entry.update(extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
            }

        # Truncate large values
        for key, value in log_entry.items():
            log_entry[key] = self.truncate_payload(value)

        return json.dumps(log_entry)


# ============================================================================
# Logging Helpers
# ============================================================================


def get_logger(name: str) -> logging.Logger:
    """Get a logger with structured formatting.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
    return logger


def log_phase_event(
    logger: logging.Logger,
    event: str,
    correlation_id: str,
    execution_id: str | None = None,
    task_id: str | None = None,
    runner_id: str | None = None,
    phase: str | None = None,
    session_id: str | None = None,
    level: int = logging.INFO,
    **extra: Any,
):
    """Log a phase event with structured data.

    Per REQ-012-10: Correlation-ID durch alle Phasen führen.

    Args:
        logger: Logger instance
        event: Event description
        correlation_id: Correlation ID for tracing
        execution_id: Execution ID
        task_id: Task ID
        runner_id: Runner ID
        phase: Current phase
        session_id: OpenCode session ID
        level: Log level
        **extra: Additional fields
    """
    extra_fields = {
        "correlation_id": correlation_id,
        "execution_id": execution_id,
        "task_id": task_id,
        "runner_id": runner_id,
        "phase": phase,
        "session_id": session_id,
        **extra,
    }
    logger.log(level, event, extra=extra_fields)


# ============================================================================
# Phase Timing Metrics
# ============================================================================


@dataclass
class PhaseMetrics:
    """Metrics for a single phase execution."""

    phase: str
    start_time: float = 0.0
    end_time: float = 0.0
    success: bool = False
    error_type: str | None = None
    correlation_id: str | None = None

    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds."""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0


class PhaseTimer:
    """Context manager for timing phase execution.

    Per REQ-012-10: Metriken ableitbar machen: Dauer je Phase.

    Usage:
        with PhaseTimer("dispatch", correlation_id="abc123") as timer:
            # phase logic
            pass

        logger.info(f"Phase {timer.phase} completed in {timer.duration_seconds:.2f}s")
    """

    def __init__(
        self,
        phase: str,
        correlation_id: str | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialize phase timer.

        Args:
            phase: Phase name
            correlation_id: Correlation ID for tracing
            logger: Logger instance (optional)
        """
        self.phase = phase
        self.correlation_id = correlation_id
        self.logger = logger or get_logger(__name__)
        self.metrics = PhaseMetrics(phase=phase, correlation_id=correlation_id)

    def __enter__(self) -> PhaseTimer:
        """Start timing."""
        self.metrics.start_time = time.time()
        log_phase_event(
            self.logger,
            f"Starting phase: {self.phase}",
            correlation_id=self.correlation_id or "unknown",
            phase=self.phase,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop timing and log result."""
        self.metrics.end_time = time.time()
        self.metrics.success = exc_type is None

        if exc_type:
            self.metrics.error_type = exc_type.__name__
            log_phase_event(
                self.logger,
                f"Phase {self.phase} failed after {self.metrics.duration_seconds:.2f}s",
                correlation_id=self.correlation_id or "unknown",
                phase=self.phase,
                level=logging.ERROR,
                error_type=self.metrics.error_type,
                duration_seconds=self.metrics.duration_seconds,
            )
        else:
            log_phase_event(
                self.logger,
                f"Phase {self.phase} completed in {self.metrics.duration_seconds:.2f}s",
                correlation_id=self.correlation_id or "unknown",
                phase=self.phase,
                duration_seconds=self.metrics.duration_seconds,
            )


@contextmanager
def measure_phase(
    phase: str,
    correlation_id: str | None = None,
    logger: logging.Logger | None = None,
) -> Generator[PhaseMetrics, None, None]:
    """Context manager for measuring phase duration.

    Args:
        phase: Phase name
        correlation_id: Correlation ID for tracing
        logger: Logger instance

    Yields:
        PhaseMetrics with timing information
    """
    timer = PhaseTimer(phase, correlation_id, logger)
    with timer:
        yield timer.metrics


# ============================================================================
# Metrics Collection
# ============================================================================


@dataclass
class ExecutionMetrics:
    """Collection of execution metrics."""

    # Counters
    executions_claimed: int = 0
    executions_completed: int = 0
    executions_failed: int = 0
    retries_scheduled: int = 0
    retries_exhausted: int = 0
    stale_executions_detected: int = 0
    adoption_conflicts: int = 0

    # Phase durations (accumulated)
    phase_durations: dict[str, float] = field(default_factory=dict)
    phase_counts: dict[str, int] = field(default_factory=dict)

    # Timestamps
    first_execution: datetime | None = None
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def record_phase_duration(self, phase: str, duration: float):
        """Record a phase duration."""
        self.phase_durations[phase] = self.phase_durations.get(phase, 0.0) + duration
        self.phase_counts[phase] = self.phase_counts.get(phase, 0) + 1
        self.last_update = datetime.now(timezone.utc)

    def get_average_phase_duration(self, phase: str) -> float:
        """Get average duration for a phase."""
        count = self.phase_counts.get(phase, 0)
        if count == 0:
            return 0.0
        return self.phase_durations.get(phase, 0.0) / count

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.executions_claimed
        if total == 0:
            return 0.0
        return self.executions_completed / total

    @property
    def retry_rate(self) -> float:
        """Calculate retry rate."""
        total = self.executions_claimed
        if total == 0:
            return 0.0
        return self.retries_scheduled / total

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "executions_claimed": self.executions_claimed,
            "executions_completed": self.executions_completed,
            "executions_failed": self.executions_failed,
            "retries_scheduled": self.retries_scheduled,
            "retries_exhausted": self.retries_exhausted,
            "stale_executions_detected": self.stale_executions_detected,
            "adoption_conflicts": self.adoption_conflicts,
            "success_rate": self.success_rate,
            "retry_rate": self.retry_rate,
            "average_phase_durations": {
                phase: self.get_average_phase_duration(phase)
                for phase in set(self.phase_durations.keys())
            },
            "first_execution": self.first_execution.isoformat() if self.first_execution else None,
            "last_update": self.last_update.isoformat(),
        }


# Global metrics instance (simple in-memory collection)
_global_metrics = ExecutionMetrics()


def get_metrics() -> ExecutionMetrics:
    """Get global metrics instance."""
    return _global_metrics


def reset_metrics():
    """Reset global metrics (for testing)."""
    global _global_metrics
    _global_metrics = ExecutionMetrics()


def record_execution_claimed():
    """Record an execution claim event."""
    _global_metrics.executions_claimed += 1
    if _global_metrics.first_execution is None:
        _global_metrics.first_execution = datetime.now(timezone.utc)
    _global_metrics.last_update = datetime.now(timezone.utc)


def record_execution_completed():
    """Record a successful execution completion."""
    _global_metrics.executions_completed += 1
    _global_metrics.last_update = datetime.now(timezone.utc)


def record_execution_failed():
    """Record a failed execution."""
    _global_metrics.executions_failed += 1
    _global_metrics.last_update = datetime.now(timezone.utc)


def record_retry_scheduled():
    """Record a retry scheduling event."""
    _global_metrics.retries_scheduled += 1
    _global_metrics.last_update = datetime.now(timezone.utc)


def record_retry_exhausted():
    """Record a retry exhaustion event."""
    _global_metrics.retries_exhausted += 1
    _global_metrics.last_update = datetime.now(timezone.utc)


def record_stale_detection():
    """Record a stale execution detection."""
    _global_metrics.stale_executions_detected += 1
    _global_metrics.last_update = datetime.now(timezone.utc)


def record_adoption_conflict():
    """Record a commit adoption conflict."""
    _global_metrics.adoption_conflicts += 1
    _global_metrics.last_update = datetime.now(timezone.utc)


def record_phase_duration(phase: str, duration: float):
    """Record phase duration."""
    _global_metrics.record_phase_duration(phase, duration)
    _global_metrics.last_update = datetime.now(timezone.utc)


# ============================================================================
# Payload Redaction
# ============================================================================


class PayloadRedactor:
    """Redact sensitive data from payloads before logging.

    Per REQ-012-10: Keine großen/sensiblen Payloads landen ungeprüft in Logs.
    """

    SENSITIVE_FIELDS = [
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "credential",
        "private_key",
        "ssh_key",
    ]

    SENSITIVE_PATTERNS = [
        r"-----BEGIN.*PRIVATE KEY-----",
        r"ghp_[a-zA-Z0-9]{36}",  # GitHub personal access tokens
        r"sk-[a-zA-Z0-9]{32}",  # OpenAI-style API keys
        r"Bearer\s+[a-zA-Z0-9._-]+",  # Bearer tokens
    ]

    def __init__(self, max_payload_size: int = 10000):
        """Initialize redactor.

        Args:
            max_payload_size: Maximum payload size before truncation
        """
        self.max_payload_size = max_payload_size

    def redact(self, data: Any) -> Any:
        """Redact sensitive data from payload.

        Args:
            data: Data to redact (dict, list, or string)

        Returns:
            Redacted data
        """
        if isinstance(data, dict):
            return self._redact_dict(data)
        elif isinstance(data, list):
            return [self.redact(item) for item in data]
        elif isinstance(data, str):
            return self._redact_string(data)
        else:
            return data

    def _redact_dict(self, data: dict) -> dict:
        """Redact sensitive fields from dictionary."""
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in self.SENSITIVE_FIELDS):
                result[key] = "[REDACTED]"
            else:
                result[key] = self.redact(value)
        return result

    def _redact_string(self, data: str) -> str:
        """Redact sensitive patterns from string."""
        result = data

        # Truncate if too large
        if len(result) > self.max_payload_size:
            result = result[: self.max_payload_size] + "... [truncated]"

        # Redact patterns
        for pattern in self.SENSITIVE_PATTERNS:
            result = re.sub(pattern, "[REDACTED]", result)

        return result


# Global redactor instance
_global_redactor = PayloadRedactor()


def redact_payload(data: Any) -> Any:
    """Redact sensitive data from payload.

    Args:
        data: Data to redact

    Returns:
        Redacted data
    """
    return _global_redactor.redact(data)


# ============================================================================
# Correlation ID Helpers
# ============================================================================


def generate_correlation_id(prefix: str = "exec") -> str:
    """Generate a new correlation ID.

    Args:
        prefix: ID prefix (default: "exec")

    Returns:
        Unique correlation ID
    """
    import uuid

    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def extract_correlation_id(context: dict) -> str | None:
    """Extract correlation ID from context.

    Args:
        context: Context dictionary

    Returns:
        Correlation ID if present
    """
    return context.get("correlation_id") or context.get("X-Correlation-ID")
