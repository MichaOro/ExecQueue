"""Health endpoints for individual and aggregated health checks."""

from fastapi import APIRouter, HTTPException

from execqueue.health.models import HealthCheckResult, HealthSummary
from execqueue.health.registry import get_registered_healthchecks
from execqueue.workers.telegram.health import get_telegram_bot_healthcheck

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


@router.get("/health", summary="Global health check")
def healthcheck() -> dict[str, object]:
    """Return the aggregated health status of all components.
    
    This endpoint checks all registered components (API, Telegram Bot, etc.)
    and returns a combined status.
    """
    results = {}
    
    for check in get_registered_healthchecks():
        result = check()
        results[result.component] = result.model_dump()
    
    # Check all statuses (results.values() are dicts now)
    overall_status = "ok" if all(r["status"] == "ok" for r in results.values()) else "not_ok"
    
    return {
        "status": overall_status,
        "checks": results,
    }


@router.get("/{component}/health", summary="Component-specific health check")
def component_health(component: str) -> dict[str, object]:
    """Return health status for a specific component.
    
    Args:
        component: Component name (e.g., 'api', 'telegram_bot')
        
    Returns:
        Health status for the requested component
        
    Examples:
        GET /api/health
        GET /telegram_bot/health
    """
    result = get_health_by_component(component)
    return result.model_dump()
