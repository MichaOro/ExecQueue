"""
Health Check and Readiness Endpoints.

Provides /health and /ready endpoints for monitoring worker state and database connectivity.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from execqueue.db.engine import engine
from execqueue.models.task import Task
from execqueue.runtime import is_scheduler_enabled, get_worker_instance_id

logger = logging.getLogger(__name__)

router = APIRouter()

# Global worker state (thread-safe for single-process)
_worker_state = {
    "started_at": None,
    "instance_id": None,
    "last_task_at": None,
    "is_running": False,
    "tasks_processed": 0,
    "tasks_failed": 0,
}


def update_worker_state(**kwargs):
    """Update worker state (thread-safe)."""
    for key, value in kwargs.items():
        _worker_state[key] = value


def get_worker_state():
    """Get current worker state."""
    return _worker_state.copy()


async def check_database_connection() -> tuple[bool, float]:
    """
    Check database connectivity and measure latency.
    
    Returns:
        Tuple of (is_connected, latency_ms)
    """
    start_time = time.time()
    try:
        with Session(engine) as session:
            session.exec(select(1))
        latency_ms = (time.time() - start_time) * 1000
        return True, latency_ms
    except Exception as e:
        logger.warning(f"Database connection check failed: {e}")
        return False, 0.0


@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns 200 if worker is healthy, 503 otherwise.
    Checks:
    - Worker is running
    - Database is connected
    """
    state = get_worker_state()
    db_connected, db_latency = await check_database_connection()
    
    is_healthy = db_connected and state["is_running"]
    
    response_data = {
        "status": "healthy" if is_healthy else "unhealthy",
        "worker": {
            "running": state["is_running"],
            "instance_id": state["instance_id"] or get_worker_instance_id(),
            "uptime_seconds": round(time.time() - state["started_at"], 2) if state["started_at"] else 0,
            "last_task_at": state["last_task_at"],
            "tasks_processed": state["tasks_processed"],
            "tasks_failed": state["tasks_failed"],
        },
        "database": {
            "connected": db_connected,
            "latency_ms": round(db_latency, 2),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if not is_healthy:
        raise HTTPException(status_code=503, detail=response_data)
    
    return JSONResponse(content=response_data)


@router.get("/ready")
async def ready_check():
    """
    Readiness check endpoint.
    
    Returns 200 if worker is ready to accept tasks, 503 otherwise.
    Checks:
    - Worker is running
    - Scheduler is enabled
    """
    state = get_worker_state()
    scheduler_enabled = is_scheduler_enabled()
    
    is_ready = state["is_running"] and scheduler_enabled
    
    response_data = {
        "ready": is_ready,
        "can_accept_tasks": state["is_running"],
        "scheduler_enabled": scheduler_enabled,
        "instance_id": state["instance_id"] or get_worker_instance_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if not is_ready:
        raise HTTPException(status_code=503, detail=response_data)
    
    return JSONResponse(content=response_data)


@router.get("/version")
async def version_check():
    """Version endpoint for identifying worker version."""
    return {
        "version": "1.0.0",
        "instance_id": get_worker_instance_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
