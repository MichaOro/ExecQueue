"""Telegram bot commands and command list."""

from __future__ import annotations

import inspect
import logging

import httpx

from execqueue.health.service import get_overall_health, render_health_report, status_to_emoji
from execqueue.settings import get_settings
from execqueue.workers.telegram.api_client import api_client
from execqueue.workers.telegram.auth import get_user_info
from execqueue.workers.telegram.git_helper import (
    get_current_branch,
    get_local_branches,
    validate_branch_name,
    GitTimeoutError,
    GitRepositoryError,
)
from execqueue.workers.telegram.git_writer import create_branch

logger = logging.getLogger(__name__)

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import CallbackContext, ConversationHandler, CallbackQueryHandler

    TELEGRAM_AVAILABLE = True
    TELEGRAM_KEYBOARD_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None  # type: ignore
    CallbackContext = None  # type: ignore
    ConversationHandler = None  # type: ignore
    InlineKeyboardButton = None  # type: ignore
    InlineKeyboardMarkup = None  # type: ignore
    CallbackQueryHandler = None  # type: ignore
    TELEGRAM_KEYBOARD_AVAILABLE = False


CREATE_TASK_TYPE = 1
CREATE_TITLE = 2
CREATE_PROMPT = 3

# NEW: States for interactive task creation flow with branch selection
BRANCH_CHOICE = 4  # Choice between existing/new/automatic
BRANCH_SELECT = 5  # Selection of an existing branch from the list
BRANCH_NAME = 6    # Input of a new branch name
CONFIRMATION = 7   # Summary and confirmation before creating

# Callback data constants for inline keyboard (reserved for future use)
TYPE_PLANNING = "planning"
TYPE_EXECUTION = "execution"
TYPE_ANALYSIS = "analysis"
TYPE_REQUIREMENT = "requirement"
BRANCH_CHOICE_EXISTING = "existing"
BRANCH_CHOICE_NEW = "new"
CONFIRM_YES = "confirm_yes"
CONFIRM_NO = "confirm_no"
BRANCH_BACK = "branch_back"


def _confirmation_keyboard() -> InlineKeyboardMarkup | None:
    """Create inline keyboard with Yes/No confirmation buttons.
    
    Returns None if TELEGRAM_KEYBOARD_AVAILABLE is False.
    """
    if not TELEGRAM_KEYBOARD_AVAILABLE:
        return None
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Ja", callback_data=CONFIRM_YES),
            InlineKeyboardButton("❌ Nein", callback_data=CONFIRM_NO),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def _get_branch_validation_detail(branch_name: str) -> str:
    """Get specific validation error message for a branch name.
    
    Returns a user-friendly explanation of why the branch name is invalid.
    """
    if not branch_name:
        return "Der Name ist leer."
    
    if len(branch_name) > 255:
        return f"Name ist zu lang ({len(branch_name)} Zeichen, max 255)."
    
    if " " in branch_name:
        return "Leerzeichen sind nicht erlaubt."
    
    if "~" in branch_name:
        return "Das Zeichen '~' ist nicht erlaubt."
    
    if "^" in branch_name:
        return "Das Zeichen '^' ist nicht erlaubt."
    
    if ":" in branch_name:
        return "Das Zeichen ':' ist nicht erlaubt."
    
    if "?" in branch_name or "*" in branch_name:
        return "Wildcards (?/*) sind nicht erlaubt."
    
    if branch_name.startswith("/") or branch_name.endswith("/"):
        return "Der Name darf nicht mit / beginnen oder enden."
    
    if branch_name.startswith("-"):
        return "Der Name darf nicht mit - beginnen."
    
    if branch_name.endswith(".lock"):
        return "Der Name darf nicht mit .lock enden."
    
    if ".." in branch_name:
        return "Zwei Punkte (..) sind nicht erlaubt."
    
    return "Der Name enthaelt ungültige Zeichen oder Muster."


def _try_get_current_branch() -> str | None:
    """Return the active branch when available, otherwise None."""
    try:
        return get_current_branch()
    except (GitTimeoutError, GitRepositoryError):
        return None


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


async def trigger_system_restart(user_telegram_id: int | None = None) -> tuple[bool, str]:
    """Trigger system restart via API.
    
    Args:
        user_telegram_id: The Telegram user ID of the requesting admin.
    """
    settings = get_settings()
    url = f"http://{settings.execqueue_api_host}:{settings.execqueue_api_port}/restart"
    headers: dict[str, str] = {}

    # Authentication handling
    if user_telegram_id is not None:
        # Prefer Telegram user ID authentication when provided
        headers["X-Telegram-User-ID"] = str(user_telegram_id)
    else:
        # Fall back to admin token authentication
        token = settings.system_admin_token
        if not token:
            return False, "system_admin_token is not configured"
        headers["X-Admin-Token"] = token

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            return True, data.get("message", "System restart initiated successfully.")

        error_msg = _read_error_detail(response) or "Unknown error"
        return False, f"Restart failed: {error_msg}"
    except httpx.TimeoutException:
        return False, "Restart request timed out."
    except Exception:
        logger.exception("Unexpected error while triggering system restart")
        return False, "Restart failed due to an unexpected error."


def get_start_message(role: str | None = None, is_active: bool = False) -> str:
    """Generate the welcome message for /start."""
    commands = get_command_list()
    message = "\U0001F44B Welcome to ExecQueue Bot!\n\n"
    message += "Available commands:\n"

    for cmd in commands:
        message += f"/{cmd['command']} - {cmd['description']}\n"

    if is_active and role == "user":
        message += "/help - Show help and usage information\n"
    elif is_active and role in {"admin", "operator"}:
        message += "/help - Show help and usage information\n"
        for cmd in get_operator_start_command_list():
            if cmd["command"] != "help":
                message += f"/{cmd['command']} - {cmd['description']}\n"

    return message


def get_help_message(role: str | None = None, is_active: bool = False) -> str:
    """Generate the role-based help message."""
    message = "\U0001F4D6 *ExecQueue Bot Help*\n\n"

    if is_active:
        message += "/status <ID> - Aufgabestatus abfragen\n"

        if role in {"admin", "operator"}:
            message += "/help - Show help and usage information\n"
            message += "/health - Check system health status\n"
            message += "\n\U0001F4DD Aufgaben:\n"
            message += "/create - Neue Aufgabe erstellen\n"

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
            "\u274C Ihr Konto ist nicht aktiv. Bitte kontaktieren Sie einen Administrator."
        )
        return _conversation_end()

    if role not in ["admin", "operator"]:
        await update.message.reply_text(
            "\u274C Zugriff verweigert. Dieser Befehl ist nur fuer Administratoren und Operatoren verfuegbar."
        )
        return _conversation_end()

    if context is not None:
        context.user_data["created_by_ref"] = str(update.effective_user.id)

    # Show inline keyboard for task type selection
    if TELEGRAM_KEYBOARD_AVAILABLE:
        keyboard = [
            [
                InlineKeyboardButton("\U0001F4C5 Planning", callback_data=TYPE_PLANNING),
                InlineKeyboardButton("\U0001F6E0\U0000FE0F Execution", callback_data=TYPE_EXECUTION),
            ],
            [
                InlineKeyboardButton("\U0001F50D Analysis", callback_data=TYPE_ANALYSIS),
                InlineKeyboardButton("\U0001F4DD Requirement", callback_data=TYPE_REQUIREMENT),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "\U0001F4DD *Aufgabe erstellen*\n\n"
            "Welchen Typ moechten Sie erstellen?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        create_message = (
            "\U0001F4DD *Aufgabe erstellen*\n\n"
            "Welchen Typ moechten Sie erstellen?\n\n"
            "1 - Planning\n"
            "2 - Execution\n"
            "3 - Analysis\n"
            "4 - Requirement"
        )
        await update.message.reply_text(create_message, parse_mode="Markdown")
    
    return CREATE_TASK_TYPE


async def create_task_type_callback(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle task type selection via inline keyboard."""
    if not update or not update.callback_query or context is None:
        return _conversation_end()

    query = update.callback_query
    await query.answer()  # Acknowledge callback - IMPORTANT!

    task_type = query.data
    context.user_data["type"] = task_type

    if task_type == TYPE_REQUIREMENT:
        await query.edit_message_text(
            # 📜  =  \U0001F4DD  (Unicode‑Code‑Point für das “Scroll”‑Emoji)
            "\U0001F4DD *Requirement*\n\n"
            "Bitte geben Sie den Titel ein:",
            parse_mode="Markdown",
        )
        return CREATE_TITLE

    await query.edit_message_text(
        f"\u2705 *{task_type.capitalize()}*\n\n"
        "Bitte geben Sie den Prompt/Inhalt ein:",
        parse_mode="Markdown"
    )
    return CREATE_PROMPT


async def create_task_type(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle the task-type selection step."""
    if not update or not update.message or context is None:
        return _conversation_end()

    text = update.message.text.strip()
    if text == "1":
        context.user_data["type"] = "planning"
    elif text == "2":
        context.user_data["type"] = "execution"
    elif text == "3":
        context.user_data["type"] = "analysis"
    elif text == "4":
        context.user_data["type"] = "requirement"
        await update.message.reply_text(
            "\U0001F4DD Bitte geben Sie den Requirement-Titel ein:"
        )
        return CREATE_TITLE
    else:
        await update.message.reply_text(
            "\u274C Ungueltige Auswahl. Bitte 1, 2, 3 oder 4 eingeben."
        )
        return CREATE_TASK_TYPE

    await update.message.reply_text("\U0001F4DD Bitte geben Sie den Prompt/Inhalt ein:")
    return CREATE_PROMPT


async def create_title(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Collect the requirement title before asking for the prompt."""
    if not update or not update.message or context is None:
        return _conversation_end()

    title = update.message.text.strip()
    if not title:
        await update.message.reply_text(
            "\u274C Requirement-Titel darf nicht leer sein."
        )
        return CREATE_TITLE

    context.user_data["title"] = title
    await update.message.reply_text("\U0001F4DD Bitte geben Sie den Prompt/Inhalt ein:")
    return CREATE_PROMPT


async def create_prompt(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle the prompt entry and move to type-specific branch selection."""
    if not update or not update.message or context is None:
        return _conversation_end()

    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text("\u274C Inhalt darf nicht leer sein.")
        return CREATE_PROMPT

    context.user_data["prompt"] = prompt
    
    # Determine next step based on task type
    task_type = context.user_data.get("type", "planning")
    
    if task_type == TYPE_REQUIREMENT:
        # Requirements can choose existing or new branch
        return await _show_branch_choice_text(update, context)

    # Planning, Execution, and Analysis use the active branch by default.
    return await _assign_current_branch_and_confirm(update, context)


async def _assign_current_branch_and_confirm(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Use the currently active branch as default and continue to confirmation."""
    if not update or context is None:
        return _conversation_end()

    try:
        active_branch = get_current_branch()
    except GitTimeoutError:
        message = (
            "\u23F0 *Zeitueberschreitung*\n\n"
            "Aktueller Branch konnte nicht rechtzeitig gelesen werden. Bitte spaeter erneut versuchen."
        )
    except GitRepositoryError as e:
        logger.error("Git repository error while reading current branch: %s", e)
        message = (
            "\u274C *Repository-Fehler*\n\n"
            f"{str(e)}\n\n"
            "Abbrechen mit /cancel"
        )
    except Exception:
        logger.exception("Unexpected error while reading current branch")
        message = (
            "\u274C *Unerwarteter Fehler*\n\n"
            "Der aktuelle Branch konnte nicht bestimmt werden. Bitte Logs pruefen."
        )
    else:
        context.user_data["branch"] = active_branch
        return await _send_confirmation_summary(update, context)

    message_obj = getattr(update, "message", None)
    if message_obj is not None:
        await message_obj.reply_text(message, parse_mode="Markdown")
    return _conversation_end()


async def _show_branch_choice_text(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Show branch choice options (for Requirements only)."""
    if not update or not update.message:
        return _conversation_end()
    
    # This now calls the keyboard function to provide a better user experience
    return await _show_branch_choice_keyboard(update, context)


async def _show_existing_branches_direct(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Show existing branches directly."""
    if not update or not update.message:
        return _conversation_end()
    
    try:
        branches = get_local_branches()
        if not branches:
            await update.message.reply_text(
                "\u26A0\ufe0f *Keine Branches gefunden*\n\n"
                "Bitte erstelle einen Branch im Repository und versuche es erneut.\n\n"
                "Abbrechen mit /cancel",
                parse_mode="Markdown"
            )
            # Cannot proceed without branches
            return _conversation_end()
        
        branch_list = "\n".join(f"{i+1}. {b}" for i, b in enumerate(branches[:10]))
        if len(branches) > 10:
            branch_list += f"\n... und {len(branches) - 10} weitere"
        
        current_branch = _try_get_current_branch()
        default_line = (
            f"0 - Aktuellen Branch verwenden ({current_branch})\n"
            if current_branch
            else ""
        )
        await update.message.reply_text(
            f"\U0001F33F *W\u00E4hle einen bestehenden Branch* ({len(branches)} verf\u00FCgbar)\n\n"
            f"{branch_list}\n\n"
            f"{default_line}"
            "Nummer eingeben:",
            parse_mode="Markdown"
        )
        return BRANCH_SELECT
        
    except GitTimeoutError:
        logger.warning("Git timeout in show_existing_branches_direct")
        await update.message.reply_text(
            "\u23F0 *Zeitueberschreitung*\n\n"
            "Git-Operation zeitueberschritten. Bitte spaeter erneut versuchen.",
            parse_mode="Markdown"
        )
        return _conversation_end()
        
    except GitRepositoryError as e:
        logger.error("Git repository error in show_existing_branches_direct: %s", e)
        await update.message.reply_text(
            "\u274C *Repository-Fehler*\n\n"
            "Repository nicht zugreifbar. Bitte pruefen:\n"
            "\u2022 Git ist installiert\n"
            "\u2022 Korrektes Verzeichnis\n"
            "\u2022 Berechtigungen\n\n"
            "Abbrechen mit /cancel",
            parse_mode="Markdown"
        )
        return _conversation_end()
        
    except Exception as e:
        logger.exception("Unexpected error in show_existing_branches_direct")
        await update.message.reply_text(
            "\u274C *Unerwarteter Fehler*\n\n"
            "Ein unbekannter Fehler ist aufgetreten. Bitte Logs pruefen.",
            parse_mode="Markdown"
        )
        return _conversation_end()


async def _show_existing_branches_callback(
    query: "CallbackQuery | None", context: "CallbackContext | None"
) -> int:
    """Show existing branches using callback query interface."""
    if not query or context is None:
        return _conversation_end()
    
    try:
        branches = get_local_branches()
        if not branches:
            await query.edit_message_text(
                "\u26A0\ufe0f *Keine Branches gefunden*\n\n"
                "Bitte erstelle einen Branch oder w\u00E4hle eine andere Option.",
                parse_mode="Markdown"
            )
            return BRANCH_CHOICE
        
        branch_list = "\n".join(f"{i+1}. {b}" for i, b in enumerate(branches[:10]))
        if len(branches) > 10:
            branch_list += f"\n... und {len(branches) - 10} weitere"
        
        current_branch = _try_get_current_branch()
        default_line = (
            f"0 - Aktuellen Branch verwenden ({current_branch})\n"
            if current_branch
            else ""
        )
        await query.edit_message_text(
            f"\U0001F33F *W\u00E4hle einen bestehenden Branch* ({len(branches)} verf\u00FCgbar)\n\n"
            f"{branch_list}\n\n"
            f"{default_line}"
            "Nummer eingeben:",
            parse_mode="Markdown"
        )
        return BRANCH_SELECT
        
    except GitTimeoutError:
        logger.warning("Git timeout in show_existing_branches_callback")
        await query.edit_message_text(
            "\u23F0 *Zeitueberschreitung*\n\n"
            "Git-Operation zeitueberschritten. Bitte spaeter erneut versuchen.",
            parse_mode="Markdown"
        )
        return BRANCH_CHOICE
        
    except GitRepositoryError as e:
        logger.error("Git repository error in show_existing_branches_callback: %s", e)
        await query.edit_message_text(
            "\u274C *Repository-Fehler*\n\n"
            "Repository nicht zugreifbar. Bitte pruefen:\n"
            "\u2022 Git ist installiert\n"
            "\u2022 Korrektes Verzeichnis\n"
            "\u2022 Berechtigungen\n\n"
            "Abbrechen mit /cancel",
            parse_mode="Markdown"
        )
        return _conversation_end()
        
    except Exception as e:
        logger.exception("Unexpected error in show_existing_branches_callback")
        await query.edit_message_text(
            "\u274C *Unerwarteter Fehler*\n\n"
            "Ein unbekannter Fehler ist aufgetreten. Bitte Logs pruefen.",
            parse_mode="Markdown"
        )
        return _conversation_end()


async def create_branch_choice(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle branch choice selection (existing/new/automatic) for Requirements.
    
    Note: This should only be called for Requirement types. For other types,
    the flow goes directly to branch selection via _show_existing_branches_direct.
    """
    if not update or not update.message or context is None:
        return _conversation_end()

    # Double-check this is a requirement
    task_type = context.user_data.get("type")
    if task_type != TYPE_REQUIREMENT:
        logger.warning("Branch choice called for non-requirement type: %s", task_type)
        return await _assign_current_branch_and_confirm(update, context)

    text = update.message.text.strip()
    
    if text == "1":
        # Choose existing branch - show list
        try:
            branches = get_local_branches()
            if not branches:
                await update.message.reply_text(
                    "\u26A0\ufe0f *Keine bestehenden Branches gefunden*\n\n"
                    "Bitte w\u00E4hle eine andere Option oder erstelle einen neuen Branch.",
                    parse_mode="Markdown"
                )
                return BRANCH_CHOICE
            
            branch_list = "\n".join(f"{i+1}. {b}" for i, b in enumerate(branches[:10]))
            if len(branches) > 10:
                branch_list += f"\n... und {len(branches) - 10} weitere"
            
            current_branch = _try_get_current_branch()
            default_line = (
                f"0 - Aktuellen Branch verwenden ({current_branch})\n"
                if current_branch
                else ""
            )
            await update.message.reply_text(
                f"\U0001F447 W\u00E4hle einen bestehenden Branch:\n\n{branch_list}\n\n"
                f"{default_line}"
                "Nummer eingeben oder 'x' zum Zurueckgehen:",
                parse_mode="Markdown"
            )
            return BRANCH_SELECT
        except GitTimeoutError:
            logger.warning("Git timeout in create_branch_choice")
            await update.message.reply_text(
                "\u23F0 *Zeitueberschreitung*\n\n"
                "Git-Operation zeitueberschritten. Bitte spaeter erneut versuchen.",
                parse_mode="Markdown"
            )
            return BRANCH_CHOICE
        except GitRepositoryError as e:
            logger.error("Git repository error in create_branch_choice: %s", e)
            await update.message.reply_text(
                "\u274C *Repository-Fehler*\n\n"
                f"{str(e)}\n\n"
                "Abbrechen mit /cancel",
                parse_mode="Markdown"
            )
            return _conversation_end()
        except Exception as e:
            logger.error("Failed to get branches: %s", e)
            await update.message.reply_text(
                "\u274C Fehler beim Lesen der Branches. "
                "Bitte versuche es erneut oder w\u00E4hle 'Neuer Branch'."
            )
            return BRANCH_CHOICE
            
    elif text == "2":
        # Create new branch - ask for name
        await update.message.reply_text(
            "\U0000270F *Neuer Branch*\n\n"
            "Gib den Namen f\u00FCr den neuen Branch ein:\n"
            "(z.B. feature/my-feature oder task-123)",
            parse_mode="Markdown"
        )
        return BRANCH_NAME
        
    else:
        await update.message.reply_text(
            "\u274C *Ungueltige Auswahl*\n\n"
            "Bitte 1 oder 2 eingeben:\n"
            "1 - Bestehenden Branch w\u00E4hlen\n"
            "2 - Neuen Branch erstellen",
            parse_mode="Markdown"
        )
        return BRANCH_CHOICE


async def create_branch_select(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle selection of an existing branch."""
    if not update or not update.message or context is None:
        return _conversation_end()

    text = update.message.text.strip()
    
    if text.lower() == "x":
        return BRANCH_CHOICE

    if text == "0":
        try:
            context.user_data["branch"] = get_current_branch()
            return await _send_confirmation_summary(update, context)
        except GitTimeoutError:
            await update.message.reply_text(
                "\u23F0 *Zeitueberschreitung*\n\n"
                "Aktueller Branch konnte nicht rechtzeitig gelesen werden.",
                parse_mode="Markdown"
            )
            return BRANCH_SELECT
        except GitRepositoryError as e:
            await update.message.reply_text(
                f"\u274C *Repository-Fehler*\n\n{str(e)}",
                parse_mode="Markdown"
            )
            return BRANCH_SELECT
    
    try:
        index = int(text) - 1
        branches = get_local_branches()
        
        if 0 <= index < len(branches):
            context.user_data["branch"] = branches[index]
            return await _send_confirmation_summary(update, context)
        else:
            await update.message.reply_text(
                f"\u274C Ung\u00FCltige Nummer. Bitte eine Zahl zwischen 1 und {len(branches)} eingeben:"
            )
            return BRANCH_SELECT
    except ValueError:
        await update.message.reply_text(
            "\u274C Bitte eine Nummer eingeben (z.B. 1, 2, 3):"
        )
        return BRANCH_SELECT


async def create_branch_name(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle input of a new branch name with enhanced validation and error handling."""
    if not update or not update.message or context is None:
        return _conversation_end()

    branch_name = update.message.text.strip()
    
    if not branch_name:
        await update.message.reply_text(
            "\u274C *Branch-Name darf nicht leer sein*\n\n"
            "Bitte einen gültigen Namen eingeben:",
            parse_mode="Markdown"
        )
        return BRANCH_NAME
    
    # Validate branch name with specific feedback
    if not validate_branch_name(branch_name):
        validation_error = _get_branch_validation_detail(branch_name)
        
        await update.message.reply_text(
            f"\u274C *Ungueltiger Branch-Name*\n\n"
            f"{validation_error}\n\n"
            "Gueltige Namen:\n"
            "\u2022 Nur a-z, A-Z, 0-9, -, _, /\n"
            "\u2022 Nicht mit / oder - beginnen\n"
            "\u2022 Nicht mit .lock enden\n"
            "\u2022 Keine Leerzeichen oder Sonderzeichen\n\n"
            "Bitte erneut eingeben:",
            parse_mode="Markdown"
        )
        return BRANCH_NAME
    
    # Try to create the branch
    try:
        success, message = create_branch(branch_name)
        if not success:
            await update.message.reply_text(
                f"\u274C *Branch-Erstellung fehlgeschlagen*\n\n"
                f"{message}\n\n"
                "Bitte anderen Namen versuchen:",
                parse_mode="Markdown"
            )
            return BRANCH_NAME
    except GitTimeoutError:
        await update.message.reply_text(
            "\u26A0\ufe0f *Zeitueberschreitung*\n\n"
            "Branch-Erstellung zu langsam. Bitte spaeter erneut versuchen.",
            parse_mode="Markdown"
        )
        return BRANCH_NAME
    except GitRepositoryError as e:
        await update.message.reply_text(
            f"\u274C *Repository-Fehler*\n\n{str(e)}\n\n"
            "Abbrechen mit /cancel",
            parse_mode="Markdown"
        )
        return _conversation_end()
    
    context.user_data["branch"] = branch_name
    # Inform user about branch creation before proceeding to confirmation
    await update.message.reply_text(
        f"\u2705 *Branch erstellt*\n\n"
        f"Branch **{branch_name}** wurde erfolgreich erstellt.",
        parse_mode="Markdown"
    )
    return await _send_confirmation_summary(update, context)


def _build_confirmation_summary(context: "CallbackContext") -> str:
    """Build the confirmation summary text from user_data."""
    summary = "Zusammenfassung:\n\n"
    summary += f"Typ: {context.user_data.get('type', 'N/A')}\n"
    if context.user_data.get("title"):
        summary += f"Titel: {context.user_data.get('title')}\n"
    summary += f"Branch: {context.user_data.get('branch', 'N/A')}\n"
    prompt = context.user_data.get("prompt", "")
    summary += f"\nPrompt: {prompt[:50]}{'...' if len(prompt) > 50 else ''}\n\n"
    if TELEGRAM_KEYBOARD_AVAILABLE:
        summary += "Bitte unten Ja oder Nein klicken:"
    else:
        summary += "Bestaetigen mit 'y' oder abbrechen mit 'n':"
    return summary


async def _send_confirmation_summary(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Send the final confirmation summary with buttons when available."""
    if not update or context is None:
        return _conversation_end()

    summary = _build_confirmation_summary(context)
    reply_markup = _confirmation_keyboard()
    update_dict = getattr(update, "__dict__", {})
    message = update_dict.get("message", getattr(update, "message", None))
    query = update_dict.get("callback_query", getattr(update, "callback_query", None))
    message_reply = getattr(message, "reply_text", None)
    query_edit = getattr(query, "edit_message_text", None)

    if query is not None and inspect.iscoroutinefunction(query_edit):
        await query_edit(
            summary,
            reply_markup=reply_markup,
        )
        return CONFIRMATION

    if message is not None and inspect.iscoroutinefunction(message_reply):
        await message_reply(summary, reply_markup=reply_markup)
        return CONFIRMATION

    return _conversation_end()


async def _execute_task_creation(context: "CallbackContext") -> tuple[bool, str]:
    """Execute the actual task creation via API. Returns (success, message)."""
    task_type = context.user_data.get("type", "planning")
    prompt = context.user_data.get("prompt", "")
    title = context.user_data.get("title")
    branch = context.user_data.get("branch")
    
    try:
        success, message = await api_client.create_task(
            task_type=task_type,
            prompt=prompt,
            created_by_ref=context.user_data.get("created_by_ref", ""),
            title=title,
            branch=branch,
        )
        return success, message
    except httpx.TimeoutException:
        logger.warning("API timeout creating task")
        return False, "API-Request zu langsam. Bitte spaeter erneut versuchen."
    except httpx.ConnectError:
        logger.error("API connection error creating task")
        return False, "Kann nicht mit dem Server verbinden."
    except Exception:
        logger.exception("Unexpected error creating task")
        return False, "Ein unbekannter Fehler ist aufgetreten."


async def create_confirmation(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle final confirmation - displays summary with Yes/No keyboard (fallback to text)."""
    if not update or context is None:
        return _conversation_end()

    # Must be a message (text input fallback) - check message first
    if update.message:
        text = update.message.text.strip().lower()
    elif update.callback_query:
        # This is a callback query (button press), delegate to the specific handlers
        return await _handle_confirmation_callback(update, context)
    else:
        return _conversation_end()
    
    if text in ["y", "ja", "yes", "ok", "1"]:
        await update.message.reply_text("\u23F3 Erstelle Aufgabe...")
        success, message = await _execute_task_creation(context)
        
        if success:
            await update.message.reply_text(f"\u2705 {message}")
        else:
            branch = context.user_data.get("branch")
            if branch and "branch" in message.lower():
                await update.message.reply_text(
                    f"\u274C *Branch-Fehler*\n\n{message}\n\n"
                    "Bitte /cancel verwenden und erneut starten.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"\u274C {message}")
        
        context.user_data.clear()
        return _conversation_end()
        
    elif text in ["n", "nein", "no", "0", "x", "cancel"]:
        await update.message.reply_text("\u274C Erstellung abgebrochen.")
        context.user_data.clear()
        return _conversation_end()
        
    else:
        # Show summary with keyboard (or text prompt if keyboard not available)
        return await _send_confirmation_summary(update, context)


async def _handle_confirmation_callback(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle confirmation callback from inline keyboard (fallback for direct calls)."""
    if not update or not update.callback_query or context is None:
        return _conversation_end()
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == CONFIRM_YES:
        return await confirm_yes(update, context)
    elif data == CONFIRM_NO:
        return await confirm_no(update, context)
    
    return CONFIRMATION


async def create_cancel(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Cancel /create conversation with guaranteed state cleanup."""
    if context is not None:
        # Always clear user_data, even if conversation wasn't active
        context.user_data.clear()
    
    if update and update.message:
        await update.message.reply_text(
            "\u274C *Erstellung abgebrochen*\n\n"
            "Alle Eingaben wurden verworfen.",
            parse_mode="Markdown"
        )
    elif update and update.callback_query:
        await update.callback_query.edit_message_text(
            "\u274C *Erstellung abgebrochen*\n\n"
            "Alle Eingaben wurden verworfen.",
            parse_mode="Markdown"
        )
    
    return _conversation_end()


async def confirm_yes(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle confirmation via Yes button."""
    if not update or not update.callback_query or context is None:
        return _conversation_end()

    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "\u23F3 *Erstelle Aufgabe...*",
        parse_mode="Markdown"
    )
    
    success, message = await _execute_task_creation(context)
    
    if success:
        await query.edit_message_text(
            f"\u2705 *{message}*",
            parse_mode="Markdown"
        )
    else:
        branch = context.user_data.get("branch")
        if branch and "branch" in message.lower():
            await query.edit_message_text(
                f"\u274C *Branch-Fehler*\n\n{message}\n\n"
                "Bitte /cancel verwenden und erneut starten.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"\u274C *Fehler*\n\n{message}",
                parse_mode="Markdown"
            )
    
    context.user_data.clear()
    return _conversation_end()


async def confirm_no(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle confirmation via No button (cancel)."""
    if not update or not update.callback_query or context is None:
        return _conversation_end()

    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "\u274C *Erstellung abgebrochen*.\n\n"
        "Alle Eingaben wurden verworfen.",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    return _conversation_end()


async def branch_choice_callback(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle branch choice selection via inline keyboard."""
    if not update or not update.callback_query or context is None:
        return _conversation_end()

    query = update.callback_query
    await query.answer()

    # Double-check this is a requirement
    task_type = context.user_data.get("type")
    if task_type != TYPE_REQUIREMENT:
        logger.warning("Branch choice called for non-requirement type: %s", task_type)
        return await _show_existing_branches_callback(query, context)

    choice = query.data
    
    if choice == BRANCH_CHOICE_EXISTING:
        return await _show_existing_branches_callback(query, context)
    elif choice == BRANCH_CHOICE_NEW:
        await query.edit_message_text(
            "\U0000270F *Neuer Branch*\n\n"
            "Gib den Namen f\u00FCr den neuen Branch ein:\n"
            "(z.B. feature/my-feature)",
            parse_mode="Markdown"
        )
        return BRANCH_NAME

    # Unknown choice
    return BRANCH_CHOICE


async def _show_existing_branches_keyboard(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Show existing branches as inline keyboard."""
    if not update or (not update.callback_query and not update.message):
        return _conversation_end()

    try:
        branches = get_local_branches()
        if not branches:
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    "\u26A0\ufe0f *Keine Branches gefunden*\n\n"
                    "Bitte erstelle einen Branch oder w\u00E4hle eine andere Option.",
                    parse_mode="Markdown"
                )
            return BRANCH_CHOICE

        # Create keyboard with max 2 branches per row
        keyboard = []
        for i in range(0, min(len(branches), 20), 2):  # Limit to 20 branches
            row = [
                InlineKeyboardButton(
                    branch,
                    callback_data=f"branch:{branch}"
                )
                for branch in branches[i:i+2]
            ]
            keyboard.append(row)

        # Add back button (only if from branch_choice)
        if update.callback_query:
            keyboard.append([InlineKeyboardButton("\u2b05\ufe0f Zur\u00FCck", callback_data=BRANCH_BACK)])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = (
            f"\U0001F33F *W\u00E4hle einen Branch* ({len(branches)} verf\u00FCgbar)\n\n"
            if update.callback_query else
            f"\U0001F33F *W\u00E4hle einen bestehenden Branch* ({len(branches)} verf\u00FCgbar)\n\n"
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        return BRANCH_SELECT

    except GitTimeoutError:
        logger.warning("Git timeout in show_existing_branches_keyboard")
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "\u23F0 *Zeitueberschreitung*\n\n"
                "Git-Operation zeitueberschritten. Bitte spaeter erneut versuchen.",
                parse_mode="Markdown"
            )
        return BRANCH_CHOICE

    except GitRepositoryError as e:
        logger.error("Git repository error in show_existing_branches_keyboard: %s", e)
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "\u274C *Repository-Fehler*\n\n"
                "Repository nicht zugreifbar. Bitte pruefen:\n"
                "\u2022 Git ist installiert\n"
                "\u2022 Korrektes Verzeichnis\n"
                "\u2022 Berechtigungen\n\n"
                "Abbrechen mit /cancel",
                parse_mode="Markdown"
            )
        return _conversation_end()

    except Exception as e:
        logger.exception("Unexpected error in show_existing_branches_keyboard")
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "\u274C *Unerwarteter Fehler*\n\n"
                "Ein unbekannter Fehler ist aufgetreten. Bitte Logs pruefen.",
                parse_mode="Markdown"
            )
        return _conversation_end()


async def branch_select_callback(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Handle branch selection from keyboard."""
    if not update or not update.callback_query or context is None:
        return _conversation_end()

    query = update.callback_query
    await query.answer()

    if query.data == BRANCH_BACK:
        # Show branch choice again
        return await _show_branch_choice_keyboard(update, context)

    if query.data.startswith("branch:"):
        branch_name = query.data.split(":", 1)[1]
        context.user_data["branch"] = branch_name
        return await _send_confirmation_summary(update, context)

    # Unknown callback, ignore
    return BRANCH_SELECT


async def _show_branch_choice_keyboard(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Show branch option selection keyboard (for Requirements only)."""
    if not update or (not update.callback_query and not update.message):
        return _conversation_end()

    keyboard = [
        [
            InlineKeyboardButton(
                "\U0001F33F Bestehenden Branch w\u00E4hlen",
                callback_data=BRANCH_CHOICE_EXISTING
            ),
        ],
        [
            InlineKeyboardButton(
                "\u2728 Neuen Branch erstellen",
                callback_data=BRANCH_CHOICE_NEW
            ),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "\U0001F33F *Branch-Auswahl*\n\n"
            "Wie moechtest du den Branch w\u00E4hlen?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    elif update.message:
        await update.message.reply_text(
            "\U0001F33F *Branch-Auswahl*\n\n"
            "Wie moechtest du den Branch w\u00E4hlen?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    return BRANCH_CHOICE


async def create_confirmation_keyboard(
    update: "Update | None", context: "CallbackContext | None"
) -> int:
    """Show confirmation summary with buttons."""
    if not update or not update.message or context is None:
        return _conversation_end()

    task_type = context.user_data.get("type", "unknown")
    title = context.user_data.get("title")
    branch = context.user_data.get("branch")
    prompt = context.user_data.get("prompt", "")

    summary = (
        f"\U0001F4DD *Zusammenfassung*\n\n"
        f"Typ: *{task_type}*\n"
    )
    if title:
        summary += f"Titel: *{title}*\n"
    summary += f"Branch: *{branch}*\n\n"
    summary += f"Prompt: _{prompt[:50]}..._\n\n"
    summary += "Best\u00E4tige die Erstellung:"

    keyboard = [
        [
            InlineKeyboardButton("\u2705 Best\u00E4tigen", callback_data=CONFIRM_YES),
            InlineKeyboardButton("\u274C Abbrechen", callback_data=CONFIRM_NO),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return CONFIRMATION


async def status_command(
    update: "Update | None", context: "CallbackContext | None"
) -> None:
    """Handle /status <task_number> command."""
    if not update or not update.message or not update.effective_user or context is None:
        return

    _, is_active = get_user_info(update.effective_user.id)
    if not is_active:
        await update.message.reply_text(
            "\u274C Ihr Konto ist nicht aktiv. Bitte kontaktieren Sie einen Administrator."
        )
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "\u274C Ungueltige Verwendung: /status <Aufgabennummer>\n\nBeispiel: /status 123"
        )
        return

    try:
        task_number = int(context.args[0])
    except ValueError:
        await update.message.reply_text("\u274C Aufgabennummer muss eine Zahl sein.")
        return

    await update.message.reply_text("\u23F3 Lade Status...")

    success, result = await api_client.get_task_status(task_number)
    if success:
        status_text = result.get("status", "unknown")
        await update.message.reply_text(
            f"\U0001F4CA *Status fuer Aufgabe #{task_number}*\n\nStatus: {status_text}",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(f"\u274C {result}")


def _get_status_emoji(status: str) -> str:
    """Get emoji for a health status."""
    return status_to_emoji(status)


def get_health_command_message() -> str:
    """Generate the compact /health response."""
    try:
        health_summary = get_overall_health()
        return render_health_report(list(health_summary.checks.values()))
    except Exception:
        logger.exception("Failed to build Telegram health message")
        return (
            "\u274C *Health Check Error*\n\n"
            "Unable to retrieve health status. Bitte Logs oder Health-Endpunkte pruefen."
        )


def _read_error_detail(response: httpx.Response) -> str | None:
    """Extract a plain-text API error detail when available."""
    try:
        payload = response.json()
    except Exception:
        return None

    if isinstance(payload, dict):
        for key in ("detail", "message"):
            value = payload.get(key)
            if isinstance(value, str):
                value = value.strip()
                if value:
                    return value

    return None


def _conversation_end() -> int:
    """Return the telegram conversation end marker when available."""
    return ConversationHandler.END if ConversationHandler else -1
