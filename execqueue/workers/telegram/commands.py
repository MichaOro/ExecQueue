"""Telegram bot commands and command list."""

from __future__ import annotations

import logging

import httpx

from execqueue.health.service import (
    get_overall_health,
    render_health_report,
    status_to_emoji,
)
from execqueue.settings import get_settings
from execqueue.workers.telegram.api_client import api_client
from execqueue.workers.telegram.auth import get_user_info

logger = logging.getLogger(__name__)

try:
    from telegram import Update
    from telegram.ext import CallbackContext, ConversationHandler

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None  # type: ignore
    CallbackContext = None  # type: ignore
    ConversationHandler = None  # type: ignore


CREATE_TASK_TYPE = 1
CREATE_PROMPT = 2


def get_command_list() -> list[dict[str, str]]:
    """Return the base command list shown to every user in /start."""
    return [
        {"command": "start", "description": "Start the bot and show available commands"},
    ]


def get_operator_start_command_list() -> list[dict[str, str]]:
    """Return additional /start commands for operators and admins."""
    return [
        {"command": "help", "description": "Show help and usage information"},
        {"command": "health", "description": "Check system health status"},
    ]


async def trigger_system_restart() -> tuple[bool, str]:
    """Trigger system restart via API."""
    settings = get_settings()
    url = f"http://{settings.execqueue_api_host}:{settings.execqueue_api_port}/restart"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url)

        if response.status_code == 200:
            data = response.json()
            return True, data.get("message", "System restart initiated successfully.")

        error_msg = _read_error_detail(response) or "Unknown error"
        return False, f"Restart failed: {error_msg}"
    except httpx.TimeoutException:
        return False, "Restart request timed out."
    except Exception as exc:
        return False, f"Restart failed: {exc}"


async def trigger_acp_restart() -> tuple[bool, str]:
    """Trigger ACP restart via API."""
    settings = get_settings()
    if not settings.acp_enabled:
        return False, "ACP ist deaktiviert. Bitte ACP_ENABLED=true setzen."

    url = (
        f"http://{settings.execqueue_api_host}:{settings.execqueue_api_port}"
        "/api/system/acp/restart"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url)

        if response.status_code == 200:
            data = response.json()
            return True, data.get("message", "ACP restart initiated successfully.")

        error_msg = _read_error_detail(response) or "Unknown error"
        return False, f"ACP restart failed: {error_msg}"
    except httpx.TimeoutException:
        return False, "ACP restart request timed out."
    except Exception as exc:
        return False, f"ACP restart failed: {exc}"


async def trigger_system_restart_all() -> tuple[bool, str]:
    """Trigger full system restart including ACP when enabled."""
    success, message = await trigger_system_restart()
    if not success:
        return success, message

    settings = get_settings()
    if not settings.acp_enabled:
        return True, "Vollständiger Neustart (System + ACP) wurde ausgelöst."

    acp_success, acp_message = await trigger_acp_restart()
    if not acp_success:
        logger.warning("ACP restart failed after system restart: %s", acp_message)
        return True, "System-Neustart wurde ausgelöst, ACP jedoch nicht."

    return True, "Vollständiger Neustart (System + ACP) wurde ausgelöst."


def get_start_message(role: str | None = None, is_active: bool = False) -> str:
    """Generate the welcome message for /start."""
    commands = get_command_list()
    message = "\U0001F44B Welcome to ExecQueue Bot!\n\n"
    message += "Available commands:\n"

    for cmd in commands:
        message += f"/{cmd['command']} - {cmd['description']}\n"

    if is_active and role in {"admin", "operator"}:
        for cmd in get_operator_start_command_list():
            message += f"/{cmd['command']} - {cmd['description']}\n"

    return message


def get_help_message(role: str | None = None, is_active: bool = False) -> str:
    """Generate the role-based help message."""
    message = "\U0001F4D6 *ExecQueue Bot Help*\n\n"

    if is_active and role in {"admin", "operator"}:
        message += "/help - Show help and usage information\n"
        message += "/health - Check system health status\n"
        message += "\n\U0001F4DD Aufgaben:\n"
        message += "/create - Neue Aufgabe erstellen\n"
        message += "/status <ID> - Aufgabestatus abfragen\n"

        if role == "admin":
            message += "\n\u2699\ufe0f Administration:\n"
            message += "/restart - System neu starten\n"
    else:
        message += "/start - Start the bot and show available commands\n"

    return message


async def create_start(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Start /create conversation for admin and operator users only."""
    if not update or not update.message or not update.effective_user:
        return _conversation_end()

    role, is_active = get_user_info(update.effective_user.id)
    if not is_active:
        await update.message.reply_text(
            "❌ Ihr Konto ist nicht aktiv. Bitte kontaktieren Sie einen Administrator."
        )
        return _conversation_end()

    if role not in ["admin", "operator"]:
        await update.message.reply_text(
            "❌ Zugriff verweigert. Dieser Befehl ist nur fuer Administratoren und Operatoren verfuegbar."
        )
        return _conversation_end()

    if context is not None:
        context.user_data["created_by_ref"] = str(update.effective_user.id)

    await update.message.reply_text(
        "📝 *Aufgabe erstellen*\n\n"
        "Welchen Typ moechten Sie erstellen?\n\n"
        "1 - Task\n"
        "2 - Requirement",
        parse_mode="Markdown",
    )
    return CREATE_TASK_TYPE


async def create_task_type(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle the task-type selection step."""
    if not update or not update.message or context is None:
        return _conversation_end()

    text = update.message.text.strip()
    if text == "1":
        context.user_data["type"] = "task"
    elif text == "2":
        context.user_data["type"] = "requirement"
    else:
        await update.message.reply_text("❌ Ungültige Auswahl. Bitte 1 oder 2 eingeben.")
        return CREATE_TASK_TYPE

    await update.message.reply_text("📝 Bitte geben Sie den Prompt/Inhalt ein:")
    return CREATE_PROMPT


async def create_prompt(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle the final prompt entry and call the task API."""
    if not update or not update.message or context is None:
        return _conversation_end()

    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text("❌ Inhalt darf nicht leer sein.")
        return CREATE_PROMPT

    await update.message.reply_text("⏳ Erstelle Aufgabe...")

    success, message = await api_client.create_task(
        task_type=context.user_data.get("type", "task"),
        prompt=prompt,
        created_by_ref=context.user_data.get("created_by_ref", ""),
    )

    if success:
        await update.message.reply_text(f"✅ {message}")
    else:
        await update.message.reply_text(f"❌ {message}")

    context.user_data.clear()
    return _conversation_end()


async def create_cancel(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Cancel /create conversation."""
    if context is not None:
        context.user_data.clear()
    if update and update.message:
        await update.message.reply_text("❌ Erstellung abgebrochen.")
    return _conversation_end()


async def status_command(
    update: "Update | None", context: "CallbackContext | None"
) -> None:
    """Handle /status <task_number> command."""
    if not update or not update.message or not update.effective_user or context is None:
        return

    _, is_active = get_user_info(update.effective_user.id)
    if not is_active:
        await update.message.reply_text(
            "❌ Ihr Konto ist nicht aktiv. Bitte kontaktieren Sie einen Administrator."
        )
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ Ungültige Verwendung: /status <Aufgabennummer>\n\nBeispiel: /status 123"
        )
        return

    try:
        task_number = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Aufgabennummer muss eine Zahl sein.")
        return

    await update.message.reply_text("⏳ Lade Status...")

    success, result = await api_client.get_task_status(task_number)
    if success:
        status_text = result.get("status", "unknown")
        await update.message.reply_text(
            f"📊 *Status fuer Aufgabe #{task_number}*\n\nStatus: {status_text}",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(f"❌ {result}")


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


def _read_error_detail(response: httpx.Response) -> str | None:
    """Extract a plain-text API error detail when available."""
    try:
        detail = response.json().get("detail")
    except Exception:
        return None

    if isinstance(detail, str):
        detail = detail.strip()
        if detail:
            return detail

    return None


def _conversation_end() -> int:
    """Return the telegram conversation end marker when available."""
    return ConversationHandler.END if ConversationHandler else -1
