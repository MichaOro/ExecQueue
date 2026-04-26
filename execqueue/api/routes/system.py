"""System-level routes that stay tenant-neutral."""

from fastapi import APIRouter

from execqueue.api.routes.health import router as health_router

router = APIRouter()
router.include_router(health_router)
