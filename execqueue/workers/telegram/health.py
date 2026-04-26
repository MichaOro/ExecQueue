"""Telegram bot health checks."""

import os
from pathlib import Path

from execqueue.health.models import HealthCheckResult


def get_telegram_bot_healthcheck() -> HealthCheckResult:
    """Return the health state of the Telegram bot component.
    
    Checks if the bot process is running by verifying the PID file
    and confirming the process exists.
    """
    # Path to the bot PID file
    ops_dir = Path(__file__).parent.parent.parent / "ops"
    pid_file = ops_dir / "pids" / "telegram_bot.pid"
    
    # Check if PID file exists
    if not pid_file.exists():
        return HealthCheckResult(
            component="telegram_bot",
            status="not_ok",
            detail="Bot PID file not found. Bot may not be running.",
        )
    
    # Read PID from file
    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, IOError) as e:
        return HealthCheckResult(
            component="telegram_bot",
            status="not_ok",
            detail=f"Failed to read bot PID file: {e}",
        )
    
    # Check if process is running
    try:
        # On Unix, kill(0) checks if process exists without sending signal
        os.kill(pid, 0)
        return HealthCheckResult(
            component="telegram_bot",
            status="ok",
            detail=f"Telegram bot is running with PID {pid}.",
        )
    except ProcessLookupError:
        return HealthCheckResult(
            component="telegram_bot",
            status="not_ok",
            detail=f"Bot process {pid} not found. PID file may be stale.",
        )
    except PermissionError:
        # Process exists but we don't have permission to signal it
        # This still means the process is running
        return HealthCheckResult(
            component="telegram_bot",
            status="ok",
            detail=f"Telegram bot is running with PID {pid} (permission limited).",
        )
    except OSError as e:
        return HealthCheckResult(
            component="telegram_bot",
            status="not_ok",
            detail=f"Failed to check bot process: {e}",
        )
