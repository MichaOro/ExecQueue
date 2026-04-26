"""Application entrypoint for ExecQueue."""

from fastapi import FastAPI

from execqueue.api.router import api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ExecQueue API",
        version="0.1.0",
        summary="Single-tenant local API prepared for shared multi-context evolution.",
        description=(
            "ExecQueue starts as a single-tenant local system and keeps a "
            "request-scoped context model so later shared multi-project or "
            "multi-tenant operation can be added cleanly."
        ),
    )
    app.include_router(api_router)
    return app


app = create_app()

