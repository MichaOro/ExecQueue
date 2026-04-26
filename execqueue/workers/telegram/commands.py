"""Telegram bot commands and command list."""

import time

from execqueue.health.service import get_overall_health


def get_command_list() -> list[dict[str, str]]:
    """Return the static list of available bot commands."""
    return [
        {"command": "start", "description": "Start the bot and show available commands"},
        {"command": "health", "description": "Check system health status"},
        {"command": "restart", "description": "Restart the system (planned)"},
    ]


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
    status_emojis = {
        "OK": "\U0001F7E2",
        "DEGRADED": "\U0001F7E1",
        "ERROR": "\U0001F534",
    }
    return status_emojis.get(status, "\U0001F534")


def get_health_command_message() -> str:
    """Generate the /health response with detailed component status."""
    try:
        health_summary = get_overall_health()

        overall_emoji = _get_status_emoji(health_summary.status)
        status_names = {"OK": "OK", "DEGRADED": "Degraded", "ERROR": "Error"}
        overall_status = status_names.get(health_summary.status, "Unknown")
        separator = "─" * 30

        message = "\U0001F3E5 *System Health Report*\n\n"
        message += f"Overall Status: {overall_emoji} *{overall_status}*\n\n"
        message += f"{separator}\n"
        message += "*Component Status:*\n"
        message += f"{separator}\n"

        for component, result in health_summary.checks.items():
            emoji = _get_status_emoji(result.status)
            status_name = status_names.get(result.status, result.status)
            formatted_name = component.replace("_", " ").title()

            message += f"\n{emoji} *{formatted_name}*\n"
            message += f"   Status: {status_name}\n"
            message += f"   Detail: {result.detail}\n"

        message += f"\n{separator}"
        message += f"\n\U0001F4CB Last updated: {time.monotonic():.0f}s ago"

        return message

    except Exception as exc:
        return (
            "\u274C *Health Check Error*\n\n"
            "Unable to retrieve health status.\n"
            f"Error: {exc}"
        )


def get_restart_command_message() -> str:
    """Generate response for /restart command."""
    return "\U0001F504 Restart command is planned but not yet implemented."
