"""Health endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Global health check")
def healthcheck() -> dict[str, str]:
    """Return a tenant-independent health response."""
    return {"status": "ok"}

