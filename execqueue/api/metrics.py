"""
Prometheus Metrics Endpoint.

Provides /metrics endpoint with Prometheus-formatted metrics for monitoring.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)
from sqlmodel import Session, select

from execqueue.db.engine import engine
from execqueue.models.task import Task

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Task Metrics
# ============================================================================

# Counter: Total number of tasks processed
tasks_processed_total = Counter(
    "execqueue_tasks_processed_total",
    "Total number of tasks processed",
    ["status"],  # done, failed, retry
    registry=REGISTRY,
)

# Counter: Total number of task retries
task_retries_total = Counter(
    "execqueue_task_retries_total",
    "Total number of task retries",
    ["source_type"],  # requirement, work_package
    registry=REGISTRY,
)

# Histogram: Task processing duration (seconds)
task_duration_seconds = Histogram(
    "execqueue_task_duration_seconds",
    "Time spent processing a task (seconds)",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
    registry=REGISTRY,
)

# ============================================================================
# Queue Metrics
# ============================================================================

# Gauge: Current queue length
queue_length = Gauge(
    "execqueue_queue_length",
    "Number of tasks currently in queue",
    registry=REGISTRY,
)

# Gauge: Number of tasks in progress
tasks_in_progress = Gauge(
    "execqueue_tasks_in_progress",
    "Number of tasks currently being processed",
    registry=REGISTRY,
)

# ============================================================================
# Error Metrics
# ============================================================================

# Counter: Total number of errors
errors_total = Counter(
    "execqueue_errors_total",
    "Total number of errors",
    ["error_type"],  # validation_error, execution_error, database_error, timeout, connection_error
    registry=REGISTRY,
)

# Counter: OpenCode API errors
opencode_api_errors_total = Counter(
    "execqueue_opencode_api_errors_total",
    "Total number of OpenCode API errors",
    ["status_code"],
    registry=REGISTRY,
)

# ============================================================================
# Worker Metrics
# ============================================================================

# Gauge: Number of active workers (should be set externally)
worker_count = Gauge(
    "execqueue_worker_count",
    "Number of active workers",
    registry=REGISTRY,
)


def update_queue_length():
    """Update the queue length metric."""
    try:
        with Session(engine) as session:
            count = session.exec(
                select(func.count(Task.id)).where(Task.status == "queued")
            ).one()
            queue_length.set(count)
    except Exception as e:
        logger.warning(f"Failed to update queue length: {e}")


def increment_task_processed(status: str):
    """Increment task processed counter."""
    tasks_processed_total.labels(status=status).inc()


def increment_task_retry(source_type: str):
    """Increment task retry counter."""
    task_retries_total.labels(source_type=source_type).inc()


def observe_task_duration(duration_seconds: float):
    """Record task duration."""
    task_duration_seconds.observe(duration_seconds)


def increment_error(error_type: str):
    """Increment error counter."""
    errors_total.labels(error_type=error_type).inc()


def increment_opencode_error(status_code: str):
    """Increment OpenCode API error counter."""
    opencode_api_errors_total.labels(status_code=status_code).inc()


@router.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus text format.
    """
    # Update queue length before returning metrics
    update_queue_length()
    
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


# Helper imports (placed at bottom to avoid circular imports)
from sqlmodel import func
