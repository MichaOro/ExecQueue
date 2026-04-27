"""API-specific health checks."""

from __future__ import annotations

import httpx

from execqueue.health.models import HealthCheckResult
from execqueue.settings import get_settings


def get_api_healthcheck() -> HealthCheckResult:
    """Return API health by actively probing the running API service."""
    settings = get_settings()
    url = f"http://{settings.execqueue_api_host}:{settings.execqueue_api_port}/openapi.json"

    try:
        response = httpx.get(url, timeout=5.0)
    except httpx.TimeoutException:
        return HealthCheckResult(
            component="api",
            status="DEGRADED",
            detail="API health check timed out.",
        )
    except Exception as exc:
        return HealthCheckResult(
            component="api",
            status="DEGRADED",
            detail=f"API health check failed: {exc}",
        )

    if response.status_code == 200:
        return HealthCheckResult(
            component="api",
            status="OK",
            detail="API responded successfully.",
        )

    return HealthCheckResult(
        component="api",
        status="DEGRADED",
        detail=f"API health check returned status {response.status_code}.",
    )
