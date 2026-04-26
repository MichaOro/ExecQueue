"""ACP health check implementation."""

import json
from datetime import datetime, timezone
from pathlib import Path

from execqueue.health.models import HealthCheckResult
from execqueue.settings import get_settings

# ACP health status file location
PROJECT_ROOT = Path(__file__).parent.parent
ACP_HEALTH_FILE = PROJECT_ROOT / "ops" / "health" / "acp.json"

# Staleness threshold in seconds (consistent with Telegram bot)
ACP_HEALTH_STALE_THRESHOLD = 60


def get_acp_healthcheck() -> HealthCheckResult:
    """Return the health state of the ACP component.

    ACP can have three states:
    - OK: ACP is enabled and running
    - DEGRADED: ACP is disabled (not an error, just unavailable)
    - ERROR: ACP is enabled but not responding

    Returns:
        HealthCheckResult: The health status of ACP component.
    """
    settings = get_settings()

    # ACP disabled is not an error - it's a valid configuration state
    if not settings.acp_enabled:
        return HealthCheckResult(
            component="acp",
            status="DEGRADED",
            detail="ACP is disabled (ACP_ENABLED=false).",
        )

    # Check if ACP health status file exists
    if not ACP_HEALTH_FILE.exists():
        return HealthCheckResult(
            component="acp",
            status="ERROR",
            detail="ACP status file not found. ACP may not be running.",
        )

    # Read and parse ACP status from file
    try:
        acp_data = json.loads(ACP_HEALTH_FILE.read_text(encoding="utf-8"))
        status = acp_data.get("status", "error")
        last_check_str = acp_data.get("last_check", "")

        # Check staleness
        if last_check_str:
            try:
                last_check = datetime.fromisoformat(
                    last_check_str.replace("Z", "+00:00")
                )
                now = datetime.now(timezone.utc)
                age = (now - last_check).total_seconds()

                if age > ACP_HEALTH_STALE_THRESHOLD:
                    return HealthCheckResult(
                        component="acp",
                        status="ERROR",
                        detail=f"ACP status is stale ({int(age)}s old).",
                    )
            except (ValueError, TypeError):
                pass

        # Map status values to normalized format
        status_mapping = {
            "ok": "OK",
            "degraded": "DEGRADED",
            "error": "ERROR",
            "starting": "DEGRADED",  # Starting is treated as degraded
        }
        normalized_status = status_mapping.get(status, "ERROR")

        # Build detail message
        detail = acp_data.get("detail", "ACP status unknown.")
        if last_check_str:
            detail = f"{detail} (last check: {last_check_str})"

        return HealthCheckResult(
            component="acp",
            status=normalized_status,
            detail=detail,
        )

    except json.JSONDecodeError as e:
        return HealthCheckResult(
            component="acp",
            status="ERROR",
            detail=f"ACP status file contains invalid JSON: {e}",
        )
    except Exception as e:
        return HealthCheckResult(
            component="acp",
            status="ERROR",
            detail=f"Failed to read ACP health: {e}",
        )


def write_acp_health_status(status: str, detail: str = "") -> None:
    """Write ACP health status to file for health check consumption.

    Args:
        status: Status string (ok, degraded, error, starting).
        detail: Optional detail message.
    """
    ACP_HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)

    health_data = {
        "component": "acp",
        "status": status,
        "detail": detail,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }

    try:
        ACP_HEALTH_FILE.write_text(json.dumps(health_data, indent=2), encoding="utf-8")
    except Exception as exc:
        # Log error but don't raise - health status write should not fail the caller
        import logging

        logger = logging.getLogger(__name__)
        logger.error("Failed to write ACP health status: %s", exc)
