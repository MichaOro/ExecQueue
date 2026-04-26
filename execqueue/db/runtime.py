"""Minimal database runtime helpers."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from execqueue.settings import Settings, get_settings


def get_database_url(settings: Settings | None = None) -> str:
    """Return the active database URL for the current runtime."""
    runtime_settings = settings or get_settings()
    return runtime_settings.active_database_url


def describe_database_target(settings: Settings | None = None) -> dict[str, str]:
    """Return redacted database connection details safe for logs and diagnostics."""
    runtime_settings = settings or get_settings()
    return {
        "environment": runtime_settings.app_env.value,
        "role": "test" if runtime_settings.is_test_environment else "primary",
        "dsn": redact_database_url(runtime_settings.active_database_url),
    }


def redact_database_url(database_url: str) -> str:
    """Remove credentials from a database URL before logging it."""
    parsed = urlsplit(database_url)
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    username = f"{parsed.username}:***@" if parsed.username else ""
    netloc = f"{username}{hostname}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
