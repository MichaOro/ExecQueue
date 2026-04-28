"""Health endpoints grouped by technical domain for OpenAPI/Swagger."""

from fastapi import APIRouter

from execqueue.api.health import get_api_healthcheck
from execqueue.db.health import get_database_healthcheck
from execqueue.health.models import HealthCheckResult
from execqueue.health.service import aggregate_system_status
from execqueue.opencode.health import get_opencode_healthcheck
from execqueue.workers.telegram.health import get_telegram_bot_healthcheck

router = APIRouter()


def _get_explicit_healthchecks() -> dict[str, HealthCheckResult]:
    """Resolve all explicit component and service health checks."""
    results = {
        "api": get_api_healthcheck(),
        "database": get_database_healthcheck(),
        "telegram_bot": get_telegram_bot_healthcheck(),
    }

    try:
        results["opencode"] = get_opencode_healthcheck()
    except Exception as exc:
        results["opencode"] = HealthCheckResult(
            component="opencode",
            status="ERROR",
            detail=f"OpenCode health check failed: {exc}",
            state="unreachable",
        )

    return results


@router.get(
    "/health",
    summary="Global health check",
    operation_id="health_get",
    tags=["System"],
)
def healthcheck() -> dict[str, object]:
    """Return the aggregated health status of all explicit component checks.
    
    The overall status reflects only the core system components (API, Database,
    Telegram Bot). Optional integrations like OpenCode are included in the
    checks output but do not affect the core system status.
    """
    checks = _get_explicit_healthchecks()
    # Exclude optional components from core status aggregation
    overall_status = aggregate_system_status(checks.values(), exclude_optional=True)

    return {
        "status": overall_status,
        "checks": {name: result.model_dump() for name, result in checks.items()},
    }


@router.get(
    "/api/health",
    summary="API component health check",
    operation_id="api_component_health_get",
    tags=["API"],
)
def api_component_health() -> dict[str, object]:
    """Return health status for the API component only."""
    return get_api_healthcheck().model_dump()


@router.get(
    "/db/health",
    summary="Database connectivity check",
    operation_id="database_connectivity_get",
    tags=["DB"],
)
def database_component_health() -> dict[str, object]:
    """Return database connectivity status only."""
    return get_database_healthcheck().model_dump()


@router.get(
    "/telegram-bot/health",
    summary="Telegram bot component health check",
    operation_id="telegram_bot_component_health_get",
    tags=["Telegram Bot"],
)
def telegram_bot_component_health() -> dict[str, object]:
    """Return health status for the Telegram bot component only."""
    return get_telegram_bot_healthcheck().model_dump()


@router.get(
    "/opencode/health",
    summary="OpenCode component health check",
    operation_id="opencode_component_health_get",
    tags=["OpenCode"],
)
def opencode_component_health() -> dict[str, object]:
    """Return OpenCode endpoint reachability without managing its lifecycle."""
    return get_opencode_healthcheck().model_dump()
