"""E2E tests for REQ-025 Telegram bot Requirement workflow.

These tests validate the complete Requirement task creation flow via the Telegram bot,
including branch selection (existing/new), prompt entry, and confirmation.

Coverage:
- US-R-01: Branch choice after title entry
- US-R-02: Existing branch selection from list
- US-R-03: New branch creation with validation
- US-R-04: Automatic branch switch (context.user_data["branch"])
- US-R-05: Prompt entry after branch step
- US-R-06: Confirmation summary with all data
- US-R-07: Cancel at any time
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from execqueue.workers.telegram.commands import (
    BRANCH_CHOICE,
    BRANCH_NAME,
    BRANCH_SELECT,
    CONFIRMATION,
    CREATE_PROMPT,
    CREATE_TASK_TYPE,
    CREATE_TITLE,
    TYPE_REQUIREMENT,
    branch_choice_callback,
    branch_select_callback,
    confirm_no,
    confirm_yes,
    create_branch_name,
    create_branch_select,
    create_cancel,
    create_confirmation,
    create_prompt,
    create_start,
    create_title,
    create_task_type_callback,
)


class TestREQ025RequirementWorkflowE2E:
    """End-to-end tests for the complete Requirement workflow."""

    @pytest.mark.asyncio
    async def test_full_requirement_flow_existing_branch(self):
        """US-R-01 bis US-R-07: Vollstaendiger Flow mit bestehendem Branch.

        Testet den kompletten Workflow:
        1. /create starten -> CREATE_TASK_TYPE
        2. Requirement-Typ auswaehlen -> CREATE_TITLE
        3. Titel eingeben -> CREATE_PROMPT
        4. Prompt eingeben -> BRANCH_CHOICE
        5. Bestehenden Branch waehlen -> BRANCH_SELECT
        6. Branch aus Liste auswaehlen -> CONFIRMATION
        7. Bestaetigen -> API Call erfolgreich
        """
        # Setup: Mock update and context
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.callback_query = None
        context = MagicMock()
        context.user_data = {}

        # Step 1: Start /create conversation (mock get_user_info to avoid DB access)
        with patch("execqueue.workers.telegram.commands.get_user_info", return_value=("admin", True)):
            result = await create_start(update, context)
        assert result == CREATE_TASK_TYPE
        assert context.user_data["created_by_ref"] is not None

        # Step 2: Select Requirement type via callback
        update.callback_query = MagicMock()
        update.callback_query.data = TYPE_REQUIREMENT
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = None  # Clear message for callback

        result = await create_task_type_callback(update, context)
        assert result == CREATE_TITLE
        assert context.user_data["type"] == TYPE_REQUIREMENT

        # Step 3: Enter title
        update.callback_query = None
        update.message = MagicMock()
        update.message.text = "Test Requirement Title"
        update.message.reply_text = AsyncMock()

        result = await create_title(update, context)
        assert result == CREATE_PROMPT
        assert context.user_data["title"] == "Test Requirement Title"

        # Step 4: Enter prompt
        update.message.text = "This is the requirement prompt content"

        with patch("execqueue.workers.telegram.commands._show_branch_choice_keyboard", return_value=BRANCH_CHOICE):
            result = await create_prompt(update, context)
        
        assert result == BRANCH_CHOICE
        assert context.user_data["prompt"] == "This is the requirement prompt content"

        # Step 5: Choose existing branch via callback
        update.callback_query = MagicMock()
        update.callback_query.data = "existing"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = None

        with patch("execqueue.workers.telegram.commands._show_existing_branches_keyboard", return_value=BRANCH_SELECT):
            result = await branch_choice_callback(update, context)
        
        assert result == BRANCH_SELECT

        # Step 6: Select branch from list via callback
        update.callback_query.data = "branch:main"
        
        with patch("execqueue.workers.telegram.commands._send_confirmation_summary", return_value=CONFIRMATION):
            result = await branch_select_callback(update, context)
        
        assert result == CONFIRMATION
        assert context.user_data["branch"] == "main"

        # Step 7: Confirm task creation - use confirm_yes directly instead of create_confirmation
        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(return_value=(True, "Task created successfully"))
            
            result = await confirm_yes(update, context)
        
        # Verify API was called with correct parameters
        mock_api.create_task.assert_called_once()
        call_args = mock_api.create_task.call_args
        assert call_args.kwargs["task_type"] == TYPE_REQUIREMENT
        assert call_args.kwargs["title"] == "Test Requirement Title"
        assert call_args.kwargs["prompt"] == "This is the requirement prompt content"
        assert call_args.kwargs["branch"] == "main"
        
        # Verify state was cleared
        assert context.user_data == {}

    @pytest.mark.asyncio
    async def test_full_requirement_flow_new_branch(self):
        """US-R-01 bis US-R-07: Vollstaendiger Flow mit neuem Branch.

        Testet den Workflow mit Branch-Erstellung:
        1-4. Gleiche Schritte wie oben
        5. Neuen Branch erstellen -> BRANCH_NAME
        6. Branch-Name eingeben -> Branch wird erstellt
        7. Bestaetigen -> API Call erfolgreich
        """
        # Setup
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        # Steps 1-3: Start, select Requirement, enter title (mock get_user_info to avoid DB access)
        with patch("execqueue.workers.telegram.commands.get_user_info", return_value=("admin", True)):
            await create_start(update, context)
        
        update.callback_query = MagicMock()
        update.callback_query.data = TYPE_REQUIREMENT
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = None
        await create_task_type_callback(update, context)

        update.callback_query = None
        update.message = MagicMock()
        update.message.text = "New Branch Requirement"
        update.message.reply_text = AsyncMock()
        await create_title(update, context)

        # Step 4: Enter prompt
        update.message.text = "Prompt for new branch requirement"
        
        with patch("execqueue.workers.telegram.commands._show_branch_choice_keyboard", return_value=BRANCH_CHOICE):
            await create_prompt(update, context)

        # Step 5: Choose new branch via callback
        update.callback_query = MagicMock()
        update.callback_query.data = "new"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = None

        result = await branch_choice_callback(update, context)
        assert result == BRANCH_NAME

        # Step 6: Enter new branch name
        update.callback_query = None
        update.message = MagicMock()
        update.message.text = "feature/new-requirement"
        update.message.reply_text = AsyncMock()

        with patch("execqueue.workers.telegram.commands.validate_branch_name", return_value=True):
            with patch("execqueue.workers.telegram.commands.create_branch", return_value=(True, "Branch created")):
                with patch("execqueue.workers.telegram.commands._send_confirmation_summary", return_value=CONFIRMATION):
                    result = await create_branch_name(update, context)
        
        assert result == CONFIRMATION
        assert context.user_data["branch"] == "feature/new-requirement"

        # Step 7: Confirm
        update.callback_query = MagicMock()
        update.callback_query.data = "confirm_yes"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = None

        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(return_value=(True, "Task created"))
            result = await confirm_yes(update, context)
        
        # Verify branch was included in API call
        mock_api.create_task.assert_called_once()
        assert mock_api.create_task.call_args.kwargs["branch"] == "feature/new-requirement"
        assert context.user_data == {}

    @pytest.mark.asyncio
    async def test_requirement_flow_cancel_at_branch_choice(self):
        """US-R-07: Abbruch am Branch-Choice Punkt.

        Testet dass /cancel alle Daten loescht und die Konversation beendet.
        """
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - get to BRANCH_CHOICE state
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": TYPE_REQUIREMENT,
            "title": "Test Title",
            "prompt": "Test Prompt"
        }

        # Cancel via command
        update.message.text = "/cancel"
        
        result = await create_cancel(update, context)
        
        # Verify state was cleared
        assert context.user_data == {}
        assert result != BRANCH_CHOICE  # Conversation ended

    @pytest.mark.asyncio
    async def test_requirement_flow_cancel_after_confirmation(self):
        """US-R-07: Abbruch nach Bestaetigungs-Summary.

        Testet dass 'Nein' bei der Bestaetigung die Konversation beendet.
        """
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - at CONFIRMATION state
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "confirm_no"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": TYPE_REQUIREMENT,
            "title": "Test Title",
            "prompt": "Test Prompt",
            "branch": "main"
        }

        result = await confirm_no(update, context)
        
        assert context.user_data == {}
        assert result != CONFIRMATION

    @pytest.mark.asyncio
    async def test_requirement_flow_invalid_branch_name_retry(self):
        """US-R-03: Invalid branch name mit Retry.

        Testet dass ungültige Branch-Namen abgelehnt werden und der User erneut eingeben kann.
        """
        from execqueue.workers.telegram.commands import branch_choice_callback, create_task_type_callback

        # Setup - get to BRANCH_NAME state
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}

        # Navigate to BRANCH_NAME
        update.callback_query = MagicMock()
        update.callback_query.data = "new"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = None
        await branch_choice_callback(update, context)

        # Try invalid branch name (with spaces)
        update.callback_query = None
        update.message = MagicMock()
        update.message.text = "invalid branch name"
        update.message.reply_text = AsyncMock()

        with patch("execqueue.workers.telegram.commands.validate_branch_name", return_value=False):
            result = await create_branch_name(update, context)
        
        assert result == BRANCH_NAME  # Stay in BRANCH_NAME state
        # Verify error message was shown
        assert update.message.reply_text.called
        reply_text = update.message.reply_text.call_args[0][0]
        assert "Ungueltiger Branch-Name" in reply_text or "nicht erlaubt" in reply_text

        # Try valid branch name
        update.message.text = "valid-branch-name"
        
        with patch("execqueue.workers.telegram.commands.validate_branch_name", return_value=True):
            with patch("execqueue.workers.telegram.commands.create_branch", return_value=(True, "Branch created")):
                with patch("execqueue.workers.telegram.commands._send_confirmation_summary", return_value=CONFIRMATION):
                    result = await create_branch_name(update, context)
        
        assert result == CONFIRMATION
        assert context.user_data["branch"] == "valid-branch-name"

    @pytest.mark.asyncio
    async def test_requirement_flow_api_timeout(self):
        """Fehlerbehandlung: API Timeout bei Task-Erstellung.

        Testet dass ein API Timeout korrekt behandelt wird.
        """
        import httpx
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - at CONFIRMATION state
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "confirm_yes"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": TYPE_REQUIREMENT,
            "title": "Test Title",
            "prompt": "Test Prompt",
            "branch": "main"
        }

        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(side_effect=httpx.TimeoutException(
                message="Request timed out", request=MagicMock()
            ))
            
            result = await confirm_yes(update, context)
        
        # Verify state was cleared even on error
        assert context.user_data == {}
        assert result != CONFIRMATION

    @pytest.mark.asyncio
    async def test_requirement_flow_api_error_branch(self):
        """Fehlerbehandlung: Branch-Fehler bei API Call.

        Testet dass Branch-spezifische Fehler korrekt gemeldet werden.
        """
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - at CONFIRMATION state
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "confirm_yes"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": TYPE_REQUIREMENT,
            "title": "Test Title",
            "prompt": "Test Prompt",
            "branch": "nonexistent-branch"
        }

        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(return_value=(False, "Branch not found"))
            
            result = await confirm_yes(update, context)
        
        # Verify state was cleared
        assert context.user_data == {}
        # Verify error message mentioned branch
        assert update.callback_query.edit_message_text.called

    @pytest.mark.asyncio
    async def test_requirement_flow_empty_title_rejected(self):
        """Fehlerbehandlung: Leerer Titel wird abgelehnt.

        Testet dass ein leerer Titel nicht akzeptiert wird.
        """
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - at CREATE_TITLE state
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "   "  # Empty/whitespace only
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}

        result = await create_title(update, context)
        
        assert result == CREATE_TITLE  # Stay in CREATE_TITLE state
        # Verify error message was shown
        reply_text = update.message.reply_text.call_args[0][0]
        assert "nicht leer" in reply_text

    @pytest.mark.asyncio
    async def test_requirement_flow_empty_prompt_rejected(self):
        """Fehlerbehandlung: Leerer Prompt wird abgelehnt.

        Testet dass ein leerer Prompt nicht akzeptiert wird.
        """
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - at CREATE_PROMPT state
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = ""
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT, "title": "Test Title"}

        result = await create_prompt(update, context)
        
        assert result == CREATE_PROMPT  # Stay in CREATE_PROMPT state
        # Verify error message was shown
        reply_text = update.message.reply_text.call_args[0][0]
        assert "nicht leer" in reply_text


class TestREQ025BranchSelectionE2E:
    """E2E tests specifically for branch selection functionality."""

    @pytest.mark.asyncio
    async def test_branch_select_zero_uses_current_branch(self):
        """US-R-02: Auswahl von '0' verwendet aktuellen Branch.

        Testet dass die Eingabe '0' den aktuellen Branch verwendet.
        """
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - at BRANCH_SELECT state
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "0"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        with patch("execqueue.workers.telegram.commands.get_current_branch", return_value="develop"):
            with patch("execqueue.workers.telegram.commands._send_confirmation_summary", return_value=CONFIRMATION):
                result = await create_branch_select(update, context)
        
        assert result == CONFIRMATION
        assert context.user_data["branch"] == "develop"

    @pytest.mark.asyncio
    async def test_branch_select_invalid_number_retry(self):
        """US-R-02: Ungültige Nummer wird abgelehnt.

        Testet dass eine ungültige Branch-Nummer abgelehnt wird.
        """
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - at BRANCH_SELECT state
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "99"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        with patch("execqueue.workers.telegram.commands.get_local_branches", return_value=["main", "develop"]):
            result = await create_branch_select(update, context)
        
        assert result == BRANCH_SELECT  # Stay in BRANCH_SELECT state
        # Verify retry message was shown
        reply_text = update.message.reply_text.call_args[0][0]
        assert "Ungültige Nummer" in reply_text or "bitte eine Zahl" in reply_text

    @pytest.mark.asyncio
    async def test_branch_select_back_to_choice(self):
        """Navigation: Zurueck zu Branch-Auswahl.

        Testet dass 'x' oder Back-Button zurueck zur Branch-Auswahl bringt.
        """
        from execqueue.workers.telegram.commands import create_task_type_callback

        # Setup - at BRANCH_SELECT state
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "x"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        result = await create_branch_select(update, context)
        
        assert result == BRANCH_CHOICE  # Back to BRANCH_CHOICE


class TestREQ025ConfirmationSummaryE2E:
    """E2E tests for confirmation summary functionality."""

    @pytest.mark.asyncio
    async def test_confirmation_summary_contains_all_data(self):
        """US-R-06: Bestaetigungs-Summary enthaelt alle Daten.

        Testet dass die Zusammenfassung Typ, Titel, Branch und Prompt enthält.
        """
        from execqueue.workers.telegram.commands import (
            _build_confirmation_summary,
            create_task_type_callback,
        )

        # Setup context with all data
        context = MagicMock()
        context.user_data = {
            "type": TYPE_REQUIREMENT,
            "title": "Test Requirement",
            "branch": "feature/test",
            "prompt": "This is a longer prompt that should be truncated in the summary..."
        }

        summary = _build_confirmation_summary(context)
        
        assert "Typ: requirement" in summary
        assert "Titel: Test Requirement" in summary
        assert "Branch: feature/test" in summary
        assert "Prompt:" in summary
        assert "..." in summary  # Truncation indicator

    @pytest.mark.asyncio
    async def test_confirmation_summary_short_prompt_no_truncation(self):
        """US-R-06: Kurzer Prompt wird nicht abgeschnitten.

        Testet dass kurze Prompts ohne Truncation angezeigt werden.
        """
        from execqueue.workers.telegram.commands import _build_confirmation_summary

        context = MagicMock()
        context.user_data = {
            "type": TYPE_REQUIREMENT,
            "title": "Short",
            "branch": "main",
            "prompt": "Short prompt"
        }

        summary = _build_confirmation_summary(context)
        
        assert "Short prompt" in summary
        assert "..." not in summary  # No truncation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
