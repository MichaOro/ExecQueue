"""ACP health check implementation."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx

from execqueue.health.models import HealthCheckResult
from execqueue.settings import AcpOperatingMode, get_settings, resolve_acp_mode

logger = logging.getLogger(__name__)

# ACP health status file location
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACP_HEALTH_FILE = PROJECT_ROOT / "ops" / "health" / "acp.json"

# Staleness threshold in seconds (consistent with Telegram bot)
ACP_HEALTH_STALE_THRESHOLD = 60

# Probe timeout in seconds
ACP_PROBE_TIMEOUT = 5


@dataclass(frozen=True)
class ProbeResult:
    """Result of an ACP endpoint reachability probe.

    Attributes:
        reachable: Whether the endpoint is reachable
        status: Status classification (ok, timeout, http_error, protocol_mismatch, invalid_url, skipped)
        latency_ms: Optional latency in milliseconds
        message: Short, sanitized message
    """

    reachable: bool
    status: Literal[
        "ok", "timeout", "http_error", "protocol_mismatch", "invalid_url", "skipped"
    ]
    latency_ms: float | None = None
    message: str = ""


def probe_acp_endpoint() -> ProbeResult:
    """Probe the ACP endpoint for reachability.

    This function checks if the configured ACP_ENDPOINT_URL is reachable
    and responds with an expected status code. It is used to distinguish
    between process status and actual endpoint availability.

    Returns:
        ProbeResult with reachability status and details.
    """
    settings = get_settings()
    mode = resolve_acp_mode(settings)

    # Skip probe if ACP is disabled
    if mode is AcpOperatingMode.DISABLED:
        return ProbeResult(
            reachable=False,
            status="skipped",
            message="ACP is disabled, probe skipped.",
        )

    # Skip probe if no endpoint URL is configured
    if not settings.acp_endpoint_url:
        return ProbeResult(
            reachable=False,
            status="invalid_url",
            message="ACP_ENDPOINT_URL is not configured.",
        )

    # Build health check URL (append /health if not present)
    endpoint_url = settings.acp_endpoint_url
    if not endpoint_url.endswith("/health"):
        probe_url = f"{endpoint_url.rstrip('/')}/health"
    else:
        probe_url = endpoint_url

    try:
        import time

        start_time = time.monotonic()

        with httpx.Client(timeout=ACP_PROBE_TIMEOUT) as client:
            response = client.get(probe_url)

        latency_ms = (time.monotonic() - start_time) * 1000

        # Check for expected status codes (200-299)
        if 200 <= response.status_code < 300:
            return ProbeResult(
                reachable=True,
                status="ok",
                latency_ms=round(latency_ms, 2),
                message=f"ACP endpoint reachable ({int(latency_ms)}ms).",
            )
        else:
            return ProbeResult(
                reachable=False,
                status="http_error",
                message=f"ACP endpoint returned HTTP {response.status_code}.",
            )

    except httpx.TimeoutException:
        return ProbeResult(
            reachable=False,
            status="timeout",
            message=f"ACP endpoint probe timed out after {ACP_PROBE_TIMEOUT}s.",
        )
    except httpx.ConnectError:
        return ProbeResult(
            reachable=False,
            status="http_error",
            message="ACP endpoint is not reachable (connection refused).",
        )
    except httpx.InvalidURL:
        return ProbeResult(
            reachable=False,
            status="invalid_url",
            message="ACP_ENDPOINT_URL is invalid.",
        )
    except Exception:
        return ProbeResult(
            reachable=False,
            status="http_error",
            message="ACP endpoint probe failed.",
        )


def get_acp_healthcheck() -> HealthCheckResult:
    """Return the health state of the ACP component.

    ACP can have three states:
    - OK: ACP is enabled and running
    - DEGRADED: ACP is disabled (not an error, just unavailable)
    - ERROR: ACP is enabled but not responding

    Returns:
        HealthCheckResult: The health status of ACP component.
    """
    mode = resolve_acp_mode(get_settings())

    # ACP disabled is not an error - it's a valid configuration state
    if mode is AcpOperatingMode.DISABLED:
        return HealthCheckResult(
            component="acp",
            status="DEGRADED",
            detail="ACP is disabled (ACP_ENABLED=false).",
        )

    # Invalid config - treat as error
    if mode is AcpOperatingMode.INVALID_CONFIG:
        return HealthCheckResult(
            component="acp",
            status="ERROR",
            detail="ACP configuration is invalid. Check ACP settings.",
        )

    # External endpoint mode - probe the remote endpoint
    if mode is AcpOperatingMode.EXTERNAL_ENDPOINT:
        probe = probe_acp_endpoint()
        if probe.reachable:
            return HealthCheckResult(
                component="acp",
                status="OK",
                detail=f"ACP external endpoint is reachable ({probe.latency_ms}ms).",
            )
        elif probe.status == "skipped":
            return HealthCheckResult(
                component="acp",
                status="DEGRADED",
                detail="ACP external endpoint probe skipped.",
            )
        else:
            return HealthCheckResult(
                component="acp",
                status="ERROR",
                detail=probe.message,
            )

    # Local managed process mode - check health file

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

    except json.JSONDecodeError:
        return HealthCheckResult(
            component="acp",
            status="ERROR",
            detail="ACP status file contains invalid JSON.",
        )
    except Exception:
        return HealthCheckResult(
            component="acp",
            status="ERROR",
            detail="Failed to read ACP health file.",
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
        logger.error("Failed to write ACP health status: %s", exc)
