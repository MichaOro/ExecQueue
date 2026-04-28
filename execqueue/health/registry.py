"""Registry for component health checks."""

from collections.abc import Callable

from execqueue.api.health import get_api_healthcheck
from execqueue.db.health import get_database_healthcheck
from execqueue.health.models import HealthCheckResult
from execqueue.opencode.health import get_opencode_healthcheck
from execqueue.workers.telegram.health import get_telegram_bot_healthcheck

HealthCheck = Callable[[], HealthCheckResult]


def get_registered_healthchecks() -> list[HealthCheck]:
    """Return all component health checks participating in overall health."""
    return [
        get_api_healthcheck,
        get_database_healthcheck,
        get_telegram_bot_healthcheck,
        get_opencode_healthcheck,
    ]
