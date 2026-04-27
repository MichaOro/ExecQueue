"""ACP lifecycle operations.

This module provides the central authority for ACP lifecycle operations.
All API and Telegram commands should delegate to these operations rather
than implementing their own restart/start/stop logic.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from execqueue.acp.health import probe_acp_endpoint
from execqueue.settings import AcpOperatingMode, get_settings, resolve_acp_mode

logger = logging.getLogger(__name__)

# ACP restart script path
PROJECT_ROOT = Path(__file__).parent.parent
ACP_RESTART_SCRIPT = PROJECT_ROOT / "ops" / "scripts" / "acp_restart.sh"


@dataclass(frozen=True)
class LifecycleResult:
    """Result of an ACP lifecycle operation.

    Attributes:
        status: Operation status (success, skipped, disabled, external_managed, invalid_config, failed)
        operation: The operation that was attempted
        message: Short, sanitized message for operators
        details: Optional additional details (no secrets)
    """

    status: str
    operation: str
    message: str
    details: dict[str, str] | None = None


def restart_acp() -> LifecycleResult:
    """Restart ACP according to the current operating mode.

    This is the central authority for ACP restart operations. API and
    Telegram should delegate to this function rather than implementing
    their own restart logic.

    Returns:
        LifecycleResult with the operation outcome.
    """
    settings = get_settings()
    mode = resolve_acp_mode(settings)

    # Handle disabled mode
    if mode is AcpOperatingMode.DISABLED:
        return LifecycleResult(
            status="disabled",
            operation="restart",
            message="ACP is disabled. No restart performed.",
        )

    # Handle external endpoint mode
    if mode is AcpOperatingMode.EXTERNAL_ENDPOINT:
        # Check if external endpoint is reachable
        probe = probe_acp_endpoint()
        if probe.reachable:
            return LifecycleResult(
                status="external_managed",
                operation="restart",
                message="ACP is externally managed. External endpoint is reachable. No local restart performed.",
                details={"endpoint_status": "reachable", "latency_ms": str(probe.latency_ms)},
            )
        else:
            return LifecycleResult(
                status="external_managed",
                operation="restart",
                message="ACP is externally managed but endpoint is not reachable. External restart may be needed.",
                details={"endpoint_status": probe.status, "message": probe.message},
            )

    # Handle invalid config
    if mode is AcpOperatingMode.INVALID_CONFIG:
        return LifecycleResult(
            status="invalid_config",
            operation="restart",
            message="ACP configuration is invalid. Check ACP_ENABLED, ACP_AUTO_START, ACP_ENDPOINT_URL, and ACP_START_COMMAND.",
        )

    # Handle local managed process mode
    if mode is AcpOperatingMode.LOCAL_MANAGED_PROCESS:
        return _execute_local_restart()

    # Fallback
    return LifecycleResult(
        status="failed",
        operation="restart",
        message="Unknown ACP operating mode. Restart failed.",
    )


def _execute_local_restart() -> LifecycleResult:
    """Execute local ACP restart via shell script.

    This is a private helper that executes the restart script.
    The public API should use restart_acp() which handles mode logic.

    Returns:
        LifecycleResult with the operation outcome.
    """
    if not ACP_RESTART_SCRIPT.exists():
        return LifecycleResult(
            status="failed",
            operation="restart",
            message="ACP restart script not found.",
            details={"script_path": str(ACP_RESTART_SCRIPT)},
        )

    try:
        # Log the restart request
        logger.info("Initiating local ACP restart via script: %s", ACP_RESTART_SCRIPT)

        # Execute the restart script (detached)
        result = subprocess.run(
            ["bash", str(ACP_RESTART_SCRIPT), "restart"],
            capture_output=True,
            text=True,
            timeout=30,
            start_new_session=True,
        )

        if result.returncode == 0:
            return LifecycleResult(
                status="success",
                operation="restart",
                message="ACP restart initiated successfully.",
            )
        else:
            error_detail = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            return LifecycleResult(
                status="failed",
                operation="restart",
                message="ACP restart failed.",
                details={"error": error_detail},
            )

    except subprocess.TimeoutExpired:
        return LifecycleResult(
            status="failed",
            operation="restart",
            message="ACP restart timed out.",
        )
    except Exception as e:
        logger.exception("ACP restart failed with exception")
        return LifecycleResult(
            status="failed",
            operation="restart",
            message="ACP restart failed.",
            details={"error": type(e).__name__},
        )
