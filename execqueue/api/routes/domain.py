"""Home for future tenant-aware domain endpoints.

Domain endpoints stay separate from technical system endpoints such as health
checks. When shared tenant scenarios are introduced, handlers in this router
can read ``X-Tenant-ID`` request-scoped through local FastAPI dependencies on
the concrete endpoint instead of relying on global middleware or app state.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api")
