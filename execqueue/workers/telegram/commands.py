"""Telegram bot commands and command list."""

import time
from typing import Any

from execqueue.health.service import get_overall_health


def get_command_list() -> list[dict[str, str]]:
    """Return the static list of available bot commands.

    Returns:
        List of command dictionaries with 'command' and 'description' keys.
    """
    return [
        {"command": "start", "description": "Start the bot and show available commands"},
        {"command": "health", "description": "Check system health status"},
        {"command": "restart", "description": "Restart the system (planned)"},
    ]


def get_start_message() -> str:
    """Generate the welcome message for /start command.

    Returns:
        Formatted welcome message with command list.
    """
    commands = get_command_list()

    message = "👋 Welcome to ExecQueue Bot!\n\n"
    message += "Available commands:\n"

    for cmd in commands:
        message += f"/{cmd['command']} - {cmd['description']}\n"

    return message


def _get_status_emoji(status: str) -> str:
    """Get emoji for health status.
    
    Args:
        status: Health status string
        
    Returns:
        Corresponding emoji
    """
    status_emojis = {
        "ok": "🟢",
        "degraded": "🟡",
        "not_ok": "🔴",
    }
    return status_emojis.get(status, "⚪")


def get_health_command_message() -> str:
    """Generate response for /health command with detailed component status.

    Returns:
        Formatted health status message with all components listed.
    """
    try:
        health_summary = get_overall_health()
        
        # Overall status header
        overall_emoji = _get_status_emoji(health_summary.status)
        status_names = {"ok": "OK", "degraded": "Degraded", "not_ok": "Error"}
        overall_status = status_names.get(health_summary.status, "Unknown")
        
        message = f"🏥 *System Health Report*\n\n"
        message += f"Overall Status: {overall_emoji} *{overall_status}*\n\n"
        message += "─" * 30 + "\n"
        message += "*Component Status:*\n"
        message += "─" * 30 + "\n"
        
        # Individual component status
        for component, result in health_summary.checks.items():
            emoji = _get_status_emoji(result.status)
            status_name = status_names.get(result.status, "Unknown")
            
            # Format component name: replace underscores with spaces and title case
            formatted_name = component.replace("_", " ").title()
            
            message += f"\n{emoji} *{formatted_name}*\n"
            message += f"   Status: {status_name}\n"
            message += f"   Detail: {result.detail}\n"
        
        message += "\n" + "─" * 30
        message += f"\n📋 Last updated: {time.monotonic():.0f}s ago"
        
        return message
        
    except Exception as e:
        return f"❌ *Health Check Error*\n\n" \
               f"Unable to retrieve health status.\n" \
               f"Error: {str(e)}"


def get_restart_command_message() -> str:
    """Generate response for /restart command.

    Returns:
        Placeholder message indicating restart is planned.
    """
    return "🔄 Restart command is planned but not yet implemented."
