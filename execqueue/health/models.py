"""Shared health result models."""

from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    """Supported health states for components and the overall system."""

    OK = "OK"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


class HealthCheckResult(BaseModel):
    """Result of one component-specific health check."""

    component: str
    status: HealthStatus
    detail: str | None = None
    state: str | None = None


class HealthSummary(BaseModel):
    """Aggregated health summary across all registered components."""

    status: HealthStatus
    checks: dict[str, HealthCheckResult]
