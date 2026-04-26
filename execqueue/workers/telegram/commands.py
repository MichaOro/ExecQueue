"""Telegram bot commands and command list."""

from execqueue.health.service import get_overall_health, render_health_report, status_to_emoji


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


def get_restart_command_message() -> str:
    """Generate response for /restart command."""
    return "\U0001F504 Restart command is planned but not yet implemented."
