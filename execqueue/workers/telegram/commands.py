"""Telegram bot commands and command list."""


def get_command_list() -> list[dict[str, str]]:
    """Return the static list of available bot commands.

    Returns:
        List of command dictionaries with 'command' and 'description' keys.
    """
    return [
        {"command": "start", "description": "Start the bot and show available commands"},
        {"command": "health", "description": "Check system health status (planned)"},
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

    message += "\nUse /health and /restart for system control (coming soon)."

    return message


def get_health_command_message() -> str:
    """Generate response for /health command.

    Returns:
        Placeholder message indicating health check is planned.
    """
    return "🔍 Health check command is planned but not yet implemented."


def get_restart_command_message() -> str:
    """Generate response for /restart command.

    Returns:
        Placeholder message indicating restart is planned.
    """
    return "🔄 Restart command is planned but not yet implemented."
