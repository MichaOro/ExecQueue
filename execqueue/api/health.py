"""API-specific health checks."""

from execqueue.health.models import HealthCheckResult


def get_api_healthcheck() -> HealthCheckResult:
    """Return the technical health state of the FastAPI/Swagger component."""
    return HealthCheckResult(
        component="api",
        status="OK",
        detail="FastAPI application and Swagger/OpenAPI endpoints are available.",
    )

