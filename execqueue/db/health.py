"""Database health check integration."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from execqueue.db.session import create_session
from execqueue.health.models import HealthCheckResult


def get_database_healthcheck() -> HealthCheckResult:
    """Return the database connectivity state without leaking infrastructure details."""
    try:
        session = create_session()
    except ValueError:
        return HealthCheckResult(
            component="database",
            status="degraded",
            detail="Database health check is not fully configured.",
        )

    try:
        session.execute(text("SELECT 1"))
        return HealthCheckResult(
            component="database",
            status="ok",
            detail="Database connectivity check succeeded.",
        )
    except SQLAlchemyError:
        return HealthCheckResult(
            component="database",
            status="degraded",
            detail="Database connectivity check failed.",
        )
    except Exception:
        return HealthCheckResult(
            component="database",
            status="degraded",
            detail="Database health check encountered an unexpected error.",
        )
    finally:
        session.close()
