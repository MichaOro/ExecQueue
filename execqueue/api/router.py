"""Top-level API router registration."""

from fastapi import APIRouter

from execqueue.api.routes.domain import router as future_domain_router
from execqueue.api.routes.system import router as system_routes_router

system_router = APIRouter()
system_router.include_router(system_routes_router)

domain_router = APIRouter()
domain_router.include_router(future_domain_router)

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(domain_router)
