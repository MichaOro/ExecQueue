"""Shared health result models."""

from typing import Literal

from pydantic import BaseModel

HealthStatus = Literal["ok", "not_ok"]


class HealthCheckResult(BaseModel):
    """Result of one component-specific health check."""

    component: str
    status: HealthStatus
    detail: str


class HealthSummary(BaseModel):
    """Aggregated health summary across all registered components."""

    status: HealthStatus
    checks: dict[str, HealthCheckResult]

