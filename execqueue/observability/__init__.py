"""Observability package for ExecQueue.

This package provides structured logging, metrics collection, and diagnostic tools
for REQ-012-10 Observability and Betriebsdiagnose.
"""

from execqueue.observability.logging import (
    StructuredFormatter,
    PayloadRedactor,
    PhaseTimer,
    PhaseMetrics,
    ExecutionMetrics,
    get_logger,
    get_metrics,
    reset_metrics,
    redact_payload,
    generate_correlation_id,
    extract_correlation_id,
    log_phase_event,
    measure_phase,
    record_execution_claimed,
    record_execution_completed,
    record_execution_failed,
    record_retry_scheduled,
    record_retry_exhausted,
    record_stale_detection,
    record_adoption_conflict,
    record_phase_duration,
)

__all__ = [
    "StructuredFormatter",
    "PayloadRedactor",
    "PhaseTimer",
    "PhaseMetrics",
    "ExecutionMetrics",
    "get_logger",
    "get_metrics",
    "reset_metrics",
    "redact_payload",
    "generate_correlation_id",
    "extract_correlation_id",
    "log_phase_event",
    "measure_phase",
    "record_execution_claimed",
    "record_execution_completed",
    "record_execution_failed",
    "record_retry_scheduled",
    "record_retry_exhausted",
    "record_stale_detection",
    "record_adoption_conflict",
    "record_phase_duration",
]
