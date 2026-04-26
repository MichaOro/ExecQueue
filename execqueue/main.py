"""Application entrypoint for ExecQueue."""

from fastapi import FastAPI

from execqueue.api.router import api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ExecQueue API",
        version="0.1.0",
        summary="System routes stay tenant-neutral while domain routes are prepared for later tenant-aware APIs.",
        description=(
            "ExecQueue separates tenant-neutral system endpoints from a future "
            "domain API area. Later domain endpoints may process the "
            "X-Tenant-ID header request-scoped without introducing global "
            "tenant middleware or deployment-specific tenant assumptions."
        ),
    )
    app.include_router(api_router)
    return app


app = create_app()
