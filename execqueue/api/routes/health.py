"""Health endpoints."""

from fastapi import APIRouter

from execqueue.health.service import get_overall_health

router = APIRouter()


@router.get("/health", summary="Global health check")
def healthcheck() -> dict[str, object]:
    """Return the aggregated tenant-independent health response."""
    summary = get_overall_health()
    return summary.model_dump()
