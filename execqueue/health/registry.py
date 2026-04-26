"""Registry for component health checks."""

from collections.abc import Callable

from execqueue.api.health import get_api_healthcheck
from execqueue.db.health import get_database_healthcheck
from execqueue.health.models import HealthCheckResult
from execqueue.workers.telegram.health import get_telegram_bot_healthcheck

# Import ACP health check (may fail if ACP module not available)
try:
    from execqueue.acp.health import get_acp_healthcheck

    ACP_HEALTH_CHECK_AVAILABLE = True
except ImportError:
    ACP_HEALTH_CHECK_AVAILABLE = False
    get_acp_healthcheck = None  # type: ignore

HealthCheck = Callable[[], HealthCheckResult]


def get_registered_healthchecks() -> list[HealthCheck]:
    """Return all component health checks participating in overall health.

    Always includes ACP health check for consistent API response structure,
    even when ACP is disabled. The health check itself will return DEGRADED
    status when ACP is disabled.
    """
    checks = [
        get_api_healthcheck,
        get_database_healthcheck,
        get_telegram_bot_healthcheck,
    ]

    # Always include ACP health check for transparency
    # It will return DEGRADED when ACP is disabled (not ERROR)
    if ACP_HEALTH_CHECK_AVAILABLE:
        checks.append(get_acp_healthcheck)

    return checks
