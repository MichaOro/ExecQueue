"""Registry for component health checks."""

from collections.abc import Callable

from execqueue.api.health import get_api_healthcheck
from execqueue.health.models import HealthCheckResult

HealthCheck = Callable[[], HealthCheckResult]


def get_registered_healthchecks() -> list[HealthCheck]:
    """Return all component health checks participating in overall health."""
    return [
        get_api_healthcheck,
    ]

