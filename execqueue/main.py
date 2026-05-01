"""Application entrypoint for ExecQueue."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session

from execqueue.api.router import api_router
from execqueue.db.session import get_db_session
from execqueue.orchestrator.main import Orchestrator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler for startup and shutdown.
    
    On startup:
    - Recovers running workflows from previous crash/restart
    - Uses 30s timeout to prevent blocking startup
    - Logs errors but does not fail startup on recovery failure
    
    On shutdown:
    - Cleanup logic can be added here
    """
    # Startup: Recover running workflows
    logger.info("Starting application startup")
    try:
        async with get_db_session() as session:
            orchestrator = Orchestrator()
            try:
                await asyncio.wait_for(
                    orchestrator.recover_running_workflows(session),
                    timeout=30.0
                )
                logger.info("Workflow recovery completed successfully")
            except asyncio.TimeoutError:
                logger.warning("Recovery timeout after 30s, continuing startup")
            except Exception as e:
                logger.error("Recovery failed: %s", e, exc_info=True)
                # Continue startup even if recovery fails
    except Exception as e:
        logger.error("Database session error during recovery: %s", e, exc_info=True)
    
    yield
    
    # Shutdown: Cleanup logic can be added here
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ExecQueue API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "System",
                "description": "Cross-component and generic system endpoints.",
            },
            {
                "name": "API",
                "description": "Health and later endpoints for the FastAPI application layer.",
            },
            {
                "name": "DB",
                "description": "Database-focused endpoints such as connectivity and persistence checks.",
            },
            {
                "name": "Telegram Bot",
                "description": "Endpoints related to the Telegram bot worker component.",
            },
            {
                "name": "OpenCode",
                "description": "Endpoints related to the external OpenCode HTTP service.",
            },
        ],
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
