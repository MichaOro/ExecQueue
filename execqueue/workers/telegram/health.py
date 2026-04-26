"""Telegram bot health checks - reads bot's self-reported health."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from execqueue.health.models import HealthCheckResult

# Path to bot's health file
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
HEALTH_FILE = PROJECT_ROOT / "ops" / "health" / "telegram_bot.json"

# Max age for health status before considering it stale (in seconds)
HEALTH_STALE_THRESHOLD = 60


def get_telegram_bot_healthcheck() -> HealthCheckResult:
    """Return the health state of the Telegram bot component.
    
    Reads the bot's self-reported health status from a JSON file
    that the bot updates periodically.
    """
    # Check if health file exists
    if not HEALTH_FILE.exists():
        return HealthCheckResult(
            component="telegram_bot",
            status="ERROR",
            detail="Bot health file not found. Bot may not be running or health reporting not configured.",
        )
    
    # Read health status from file
    try:
        health_data = json.loads(HEALTH_FILE.read_text())
        status = health_data.get("status", "not_ok")
        detail = health_data.get("detail", "Unknown status")
        last_check_str = health_data.get("last_check", "")
        
        # Check if health status is stale
        if last_check_str:
            try:
                last_check = datetime.fromisoformat(last_check_str.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                age = (now - last_check).total_seconds()
                
                if age > HEALTH_STALE_THRESHOLD:
                    return HealthCheckResult(
                        component="telegram_bot",
                        status="ERROR",
                        detail=f"Bot health status is stale ({int(age)}s old). Bot may have crashed.",
                    )
            except (ValueError, TypeError):
                pass  # Ignore parsing errors, use the status as-is
        
        # Add last check timestamp for debugging (optional)
        if last_check_str:
            detail = f"{detail} (last check: {last_check_str})"
        
        # Map legacy status values to new enum
        status_mapping = {
            "ok": "OK",
            "degraded": "DEGRADED",
            "not_ok": "ERROR",
        }
        normalized_status = status_mapping.get(status, "ERROR")
        
        return HealthCheckResult(
            component="telegram_bot",
            status=normalized_status,
            detail=detail,
        )
    except json.JSONDecodeError as e:
        return HealthCheckResult(
            component="telegram_bot",
            status="ERROR",
            detail=f"Bot health file contains invalid JSON: {e}",
        )
    except Exception as e:
        return HealthCheckResult(
            component="telegram_bot",
            status="ERROR",
            detail=f"Failed to read bot health: {e}",
        )
