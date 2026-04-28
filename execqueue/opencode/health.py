"""OpenCode reachability and health integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import httpx

from execqueue.health.models import HealthCheckResult, HealthStatus
from execqueue.settings import OpenCodeOperatingMode, Settings, get_settings

# OpenCode reachability state taxonomy
OpenCodeState = Literal[
    "disabled",
    "invalid_config",
    "available",
    "unreachable",
    "timeout",
    "unexpected_response",
]


@dataclass(frozen=True)
class OpenCodeReachability:
    """Result of one OpenCode HTTP reachability probe."""

    state: OpenCodeState
    reachable: bool
    detail: str
    latency_ms: float | None = None
    http_status: int | None = None


def _build_probe_url(base_url: str) -> str:
    """Return the preferred probe target for OpenCode."""
    parsed = urlsplit(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/health"):
        return base_url
    return f"{base_url.rstrip('/')}/health"


def _map_http_status_to_state(status_code: int) -> tuple[OpenCodeState, bool, str]:
    """Map HTTP status code to reachability state.
    
    Returns:
        Tuple of (state, reachable, detail_message)
    """
    if 200 <= status_code < 300:
        return "available", True, f"OpenCode endpoint is available ({status_code})."
    elif 400 <= status_code < 600:
        return (
            "unexpected_response",
            False,
            f"OpenCode endpoint responded unexpectedly ({status_code}).",
        )
    else:
        # Other status codes (1xx, 3xx) are also unexpected
        return (
            "unexpected_response",
            False,
            f"OpenCode endpoint responded unexpectedly ({status_code}).",
        )


def _map_exception_to_state(
    exc: Exception, settings: Settings
) -> tuple[OpenCodeState, bool, str]:
    """Map httpx exception to reachability state.
    
    Returns:
        Tuple of (state, reachable, detail_message)
    """
    if isinstance(exc, httpx.TimeoutException):
        return (
            "timeout",
            False,
            f"OpenCode endpoint probe timed out after {settings.opencode_timeout_ms}ms.",
        )
    elif isinstance(exc, httpx.ConnectError):
        return (
            "unreachable",
            False,
            "OpenCode endpoint is not reachable (connection refused).",
        )
    elif isinstance(exc, httpx.InvalidURL):
        return (
            "invalid_config",
            False,
            "OpenCode configuration is invalid (URL malformed).",
        )
    else:
        return (
            "unreachable",
            False,
            "OpenCode endpoint probe failed.",
        )


def probe_opencode_endpoint(
    settings: Settings | None = None,
    client_factory: type[httpx.Client] = httpx.Client,
) -> OpenCodeReachability:
    """Probe the configured OpenCode endpoint without touching process state."""
    runtime_settings = settings or get_settings()

    if runtime_settings.opencode_mode is OpenCodeOperatingMode.DISABLED:
        return OpenCodeReachability(
            state="disabled",
            reachable=False,
            detail="OpenCode integration is disabled.",
        )

    probe_url = _build_probe_url(runtime_settings.opencode_base_url)
    timeout = runtime_settings.opencode_timeout_ms / 1000

    try:
        import time

        started_at = time.monotonic()
        with client_factory(timeout=timeout, follow_redirects=True) as client:
            response = client.get(probe_url)
        latency_ms = round((time.monotonic() - started_at) * 1000, 2)

        state, reachable, detail = _map_http_status_to_state(response.status_code)
        return OpenCodeReachability(
            state=state,
            reachable=reachable,
            detail=detail,
            latency_ms=latency_ms,
            http_status=response.status_code,
        )
    except Exception as exc:
        state, reachable, detail = _map_exception_to_state(exc, runtime_settings)
        return OpenCodeReachability(
            state=state,
            reachable=reachable,
            detail=detail,
        )


def _state_to_health_status(state: OpenCodeState) -> HealthStatus:
    """Map OpenCode reachability state to HealthStatus.
    
    This mapping determines whether a given state should be treated as
    OK, DEGRADED, or ERROR for health aggregation purposes.
    
    - disabled: DEGRADED (optional feature not configured)
    - invalid_config: DEGRADED (configuration issue)
    - available: OK (endpoint is healthy)
    - unreachable: DEGRADED (endpoint not reachable)
    - timeout: DEGRADED (temporary network issue)
    - unexpected_response: DEGRADED (endpoint returned unexpected status)
    """
    if state == "available":
        return HealthStatus.OK
    elif state == "disabled":
        return HealthStatus.DEGRADED
    else:
        # All other states are treated as DEGRADED
        return HealthStatus.DEGRADED


def get_opencode_healthcheck(settings: Settings | None = None) -> HealthCheckResult:
    """Map OpenCode reachability to the shared health model."""
    result = probe_opencode_endpoint(settings=settings)

    status = _state_to_health_status(result.state)
    return HealthCheckResult(
        component="opencode",
        status=status,
        detail=result.detail,
        state=result.state,
    )
