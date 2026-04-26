"""Telegram bot commands and command list."""

import httpx

from execqueue.health.service import get_overall_health, render_health_report, status_to_emoji
from execqueue.settings import get_settings


def get_command_list() -> list[dict[str, str]]:
    """Return the static list of available bot commands (for /start)."""
    return [
        {"command": "start", "description": "Start the bot and show available commands"},
        {"command": "help", "description": "Show help and usage information"},
        {"command": "health", "description": "Check system health status"},
    ]


def get_admin_command_list() -> list[dict[str, str]]:
    """Return admin-only commands for /help."""
    return [
        {"command": "restart", "description": "Restart the system (Admin only)"},
    ]


async def trigger_system_restart() -> tuple[bool, str]:
    """Trigger system restart via API.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    settings = get_settings()
    api_host = settings.execqueue_api_host
    api_port = settings.execqueue_api_port
    
    url = f"http://{api_host}:{api_port}/api/system/restart"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url)
            
            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "System restart initiated successfully.")
            else:
                error_msg = response.json().get("detail", "Unknown error")
                return False, f"Restart failed: {error_msg}"
                
    except httpx.TimeoutException:
        return False, "Restart request timed out."
    except Exception as exc:
        return False, f"Restart failed: {str(exc)}"


def get_start_message() -> str:
    """Generate the welcome message for /start command."""
    commands = get_command_list()

    message = "\U0001F44B Welcome to ExecQueue Bot!\n\n"
    message += "Available commands:\n"

    for cmd in commands:
        message += f"/{cmd['command']} - {cmd['description']}\n"

    return message


def _get_status_emoji(status: str) -> str:
    """Get emoji for a health status."""
    return status_to_emoji(status)


def get_health_command_message() -> str:
    """Generate the compact /health response."""
    try:
        health_summary = get_overall_health()
        return render_health_report(list(health_summary.checks.values()))
    except Exception as exc:
        return (
            "\u274C *Health Check Error*\n\n"
            "Unable to retrieve health status.\n"
            f"Error: {exc}"
        )
