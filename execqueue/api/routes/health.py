"""Health endpoints grouped by technical domain for OpenAPI/Swagger."""

from fastapi import APIRouter, HTTPException

from execqueue.health.models import HealthCheckResult
from execqueue.health.registry import get_registered_healthchecks

router = APIRouter()


def get_health_by_component(component: str) -> HealthCheckResult:
    """Get health status for a specific component.
    
    Args:
        component: Component name (e.g., 'api', 'telegram_bot')
        
    Returns:
        HealthCheckResult for the requested component
        
    Raises:
        HTTPException: If component not found
    """
    for check in get_registered_healthchecks():
        result = check()
        if result.component == component:
            return result
    
    raise HTTPException(status_code=404, detail=f"Component '{component}' not found")


@router.get(
    "/health",
    summary="Global health check",
    operation_id="health_get",
    tags=["System"],
)
def healthcheck() -> dict[str, object]:
    """Return the aggregated health status of all components.
    
    This endpoint checks all registered components (API, Database, Telegram Bot)
    and returns a combined status.
    """
    results = {}
    
    for check in get_registered_healthchecks():
        result = check()
        results[result.component] = result.model_dump()

    # Use the aggregation service for consistent status calculation
    from execqueue.health.service import aggregate_system_status
    
    components = [HealthCheckResult(**result) for result in results.values()]
    overall_status = aggregate_system_status(components)
    
    return {
        "status": overall_status,
        "checks": results,
    }


@router.get(
    "/health/live",
    summary="Liveness probe",
    operation_id="liveness_get",
    tags=["API"],
)
def liveness() -> dict[str, object]:
    """Return liveness status of the API.
    
    This endpoint confirms that the FastAPI application is running and
    responding to requests. It does not check external dependencies like
    the database.
    
    Use this endpoint for Kubernetes liveness probes to detect if the
    application needs to be restarted.
    """
    return {
        "status": "OK",
        "component": "api",
        "detail": "API is alive and responding.",
    }


@router.get(
    "/health/ready",
    summary="Readiness probe",
    operation_id="readiness_get",
    tags=["API"],
)
def readiness() -> dict[str, object]:
    """Return readiness status including database connectivity.
    
    This endpoint checks if the API is ready to serve traffic by verifying
    both the API itself and database connectivity.
    
    Use this endpoint for Kubernetes readiness probes to determine if the
    application should receive traffic.
    """
    from execqueue.db.health import get_database_healthcheck
    
    api_check = HealthCheckResult(
        component="api",
        status="OK",
        detail="API is ready.",
    )
    db_check = get_database_healthcheck()
    
    # Aggregate status - if DB is degraded, readiness is degraded
    from execqueue.health.service import aggregate_system_status
    
    components = [api_check, db_check]
    overall_status = aggregate_system_status(components)
    
    return {
        "status": overall_status,
        "checks": {
            "api": api_check.model_dump(),
            "database": db_check.model_dump(),
        },
    }


@router.get(
    "/health/db",
    summary="Database connectivity check",
    operation_id="db_connectivity_get",
    tags=["DB"],
)
def database_connectivity() -> dict[str, object]:
    """Return database connectivity status only.
    
    This endpoint performs a side-effect-free connectivity check against
    the configured database using a simple SELECT 1 query.
    
    Use this endpoint to verify database connectivity without checking
    other components.
    """
    from execqueue.db.health import get_database_healthcheck
    
    db_check = get_database_healthcheck()
    
    return {
        "status": db_check.status,
        "component": "database",
        "detail": db_check.detail,
    }


@router.get(
    "/api/health",
    summary="API component health check",
    operation_id="api_component_health_get",
    tags=["API"],
)
def api_component_health() -> dict[str, object]:
    """Return health status for the API component only."""
    result = get_health_by_component("api")
    return result.model_dump()


@router.get(
    "/db/health",
    summary="Database component health check",
    operation_id="database_component_health_get",
    tags=["DB"],
)
def database_component_health() -> dict[str, object]:
    """Return health status for the database component only."""
    result = get_health_by_component("database")
    return result.model_dump()


@router.get(
    "/telegram-bot/health",
    summary="Telegram bot component health check",
    operation_id="telegram_bot_component_health_get",
    tags=["Telegram Bot"],
)
def telegram_bot_component_health() -> dict[str, object]:
    """Return health status for the Telegram bot component only."""
    result = get_health_by_component("telegram_bot")
    return result.model_dump()


@router.get(
    "/acp/health",
    summary="ACP component health check",
    operation_id="acp_component_health_get",
    tags=["ACP"],
)
def acp_component_health() -> dict[str, object]:
    """Return health status for the ACP component.

    Returns DEGRADED status when ACP is disabled (ACP_ENABLED=false),
    which is not an error but indicates the component is unavailable.
    Returns ERROR when ACP is enabled but not responding.
    Returns OK when ACP is enabled and running.
    """
    result = get_health_by_component("acp")
    return result.model_dump()


@router.get(
    "/{component}/health",
    summary="Generic component-specific health check",
    operation_id="component_health_get",
    tags=["System"],
)
def component_health(component: str) -> dict[str, object]:
    """Return health status for a specific component.
    
    Args:
        component: Component name (e.g., 'api', 'database', 'telegram_bot')
        
    Returns:
        Health status for the requested component
        
    Examples:
        GET /health
        GET /api/health
        GET /db/health
        GET /telegram-bot/health
        GET /health/live
        GET /health/ready
        GET /health/db
        GET /telegram_bot/health
    """
    result = get_health_by_component(component)
    return result.model_dump()
