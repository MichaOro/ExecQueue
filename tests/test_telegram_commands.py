"""Tests for Telegram bot command handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execqueue.workers.telegram.commands import (
    BRANCH_CHOICE,
    BRANCH_NAME,
    BRANCH_SELECT,
    CONFIRMATION,
    CONFIRM_YES,
    CONFIRM_NO,
    CREATE_PROMPT,
    CREATE_TASK_TYPE,
    CREATE_TITLE,
    TYPE_REQUIREMENT,
    branch_choice_callback,
    branch_select_callback,
    confirm_yes,
    confirm_no,
    create_branch_choice,
    create_branch_name,
    create_branch_select,
    create_confirmation,
    create_confirmation_keyboard,
    create_cancel,
    create_prompt,
    create_start,
    create_title,
    create_task_type,
    get_command_list,
    get_health_command_message,
    get_help_message,
    get_start_message,
    status_command,
    trigger_system_restart,
)


class TestCommandMessages:
    def test_get_start_message_format(self):
        message = get_start_message()
        assert "Welcome to ExecQueue Bot!" in message
        assert "/start - Start the bot and show available commands" in message

    def test_get_help_message_for_admin(self):
        message = get_help_message(role="admin", is_active=True)
        assert "/create - Neue Aufgabe erstellen" in message
        assert "/status <ID> - Aufgabestatus abfragen" in message
        assert "/restart - System neu starten" in message

    def test_get_health_command_message(self):
        message = get_health_command_message()
        assert "Health" in message or "Error" in message

    def test_get_command_list(self):
        commands = get_command_list()
        assert commands == [{"command": "start", "description": "Start the bot and show available commands"}]


class TestCreateCommand:
    @pytest.mark.asyncio
    async def test_create_start_requires_active_user(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123
        context = MagicMock()

        with patch("execqueue.workers.telegram.commands.get_user_info", return_value=("user", False)):
            result = await create_start(update, context)

        assert result != CREATE_TASK_TYPE
        assert "nicht aktiv" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_start_allows_admin(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123
        context = MagicMock()
        context.user_data = {}

        with patch("execqueue.workers.telegram.commands.get_user_info", return_value=("admin", True)):
            result = await create_start(update, context)

        assert result == CREATE_TASK_TYPE
        assert context.user_data["created_by_ref"] == "123"

    @pytest.mark.asyncio
    async def test_create_task_type_selects_requirement_and_requests_title(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "4"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        result = await create_task_type(update, context)

        assert result == CREATE_TITLE
        assert context.user_data["type"] == "requirement"

    @pytest.mark.asyncio
    async def test_create_title_rejects_empty_value(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "   "
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": "requirement"}

        result = await create_title(update, context)

        assert result == CREATE_TITLE
        assert "nicht leer" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_prompt_sets_prompt_and_uses_current_branch(self):
        """Test that create_prompt stores the prompt and uses the active branch."""
        from execqueue.workers.telegram.commands import CONFIRMATION

        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "Test prompt"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": "planning", "created_by_ref": "123"}

        with patch("execqueue.workers.telegram.commands._assign_current_branch_and_confirm", return_value=CONFIRMATION):
            result = await create_prompt(update, context)

        assert result == CONFIRMATION
        assert context.user_data["prompt"] == "Test prompt"

    @pytest.mark.asyncio
    async def test_create_cancel_clears_state(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": "planning", "created_by_ref": "123"}

        result = await create_cancel(update, context)

        assert result != CREATE_PROMPT
        assert context.user_data == {}


class TestStatusCommand:
    @pytest.mark.asyncio
    async def test_status_requires_task_number(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123
        context = MagicMock()
        context.args = []

        with patch("execqueue.workers.telegram.commands.get_user_info", return_value=("admin", True)):
            await status_command(update, context)

        assert "Ungueltige Verwendung" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_status_fetches_from_api(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123
        context = MagicMock()
        context.args = ["42"]

        with patch("execqueue.workers.telegram.commands.get_user_info", return_value=("admin", True)):
            with patch("execqueue.workers.telegram.commands.api_client") as mock_client:
                mock_client.get_task_status = AsyncMock(return_value=(True, {"status": "completed"}))
                await status_command(update, context)

        mock_client.get_task_status.assert_called_once_with(42)


class TestRestartCommand:
    @pytest.mark.asyncio
    async def test_restart_command_rejects_extra_argument(self):
        from execqueue.workers.telegram.bot import restart_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123
        context = MagicMock()
        context.args = ["all"]

        with patch("execqueue.workers.telegram.auth.get_user_info", return_value=("admin", True)):
            with patch("execqueue.workers.telegram.commands.trigger_system_restart") as mock_restart:
                await restart_command(update, context)

        mock_restart.assert_not_called()
        assert "Verfuegbare Option" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_restart_command_default_system(self):
        from execqueue.workers.telegram.bot import restart_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123
        context = MagicMock()
        context.args = []

        with patch("execqueue.workers.telegram.auth.get_user_info", return_value=("admin", True)):
            with patch("execqueue.workers.telegram.commands.trigger_system_restart") as mock_restart:
                mock_restart.return_value = (True, "System restarted")
                await restart_command(update, context)

        mock_restart.assert_called_once_with(123)
        assert update.message.reply_text.call_count >= 2


class TestRestartFunctions:
    @pytest.mark.asyncio
    async def test_trigger_system_restart_sends_telegram_user_id(self):
        with patch("execqueue.workers.telegram.commands.get_settings") as mock_settings:
            mock_settings.return_value.execqueue_api_host = "127.0.0.1"
            mock_settings.return_value.execqueue_api_port = 8000

            with patch("execqueue.workers.telegram.commands.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"message": "System restarted"}
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

                success, message = await trigger_system_restart(user_telegram_id=123456789)

        # Verify the correct header was sent
        call_args = mock_client.return_value.__aenter__.return_value.post.call_args
        assert call_args[1]["headers"]["X-Telegram-User-ID"] == "123456789"
        assert "X-Admin-Token" not in call_args[1]["headers"]
        
        assert success is True
        assert message == "System restarted"

    @pytest.mark.asyncio
    async def test_trigger_system_restart_handles_api_error(self):
        with patch("execqueue.workers.telegram.commands.get_settings") as mock_settings:
            mock_settings.return_value.execqueue_api_host = "127.0.0.1"
            mock_settings.return_value.execqueue_api_port = 8000

            with patch("execqueue.workers.telegram.commands.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 403
                mock_response.json.return_value = {"detail": "Admin access required"}
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

                success, message = await trigger_system_restart(user_telegram_id=123456789)

        assert success is False
        assert "Admin access required" in message

    @pytest.mark.asyncio
    async def test_trigger_system_restart_handles_timeout(self):
        import httpx
        
        with patch("execqueue.workers.telegram.commands.get_settings") as mock_settings:
            mock_settings.return_value.execqueue_api_host = "127.0.0.1"
            mock_settings.return_value.execqueue_api_port = 8000

            with patch("execqueue.workers.telegram.commands.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.TimeoutException(
                    message="Request timed out", request=MagicMock()
                )

                success, message = await trigger_system_restart(user_telegram_id=123456789)

        assert success is False
        assert "timed out" in message.lower()


class TestBranchChoiceHandler:
    @pytest.mark.asyncio
    async def test_create_branch_choice_existing_branch(self):
        """Test branch choice with existing branch selection."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "1"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}
        
        with patch("execqueue.workers.telegram.commands.get_local_branches", return_value=["main", "develop"]):
            result = await create_branch_choice(update, context)
        
        assert result == BRANCH_SELECT
        update.message.reply_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_branch_choice_new_branch(self):
        """Test branch choice with new branch creation."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "2"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}
        
        result = await create_branch_choice(update, context)
        
        assert result == BRANCH_NAME
        update.message.reply_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_branch_choice_invalid_input(self):
        """Test branch choice with invalid input."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "3"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}
        
        result = await create_branch_choice(update, context)
        
        assert result == BRANCH_CHOICE
        update.message.reply_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_branch_choice_non_requirement_bypass(self):
        """Test that non-requirement types bypass branch choice."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "1"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": "planning"}
        
        with patch("execqueue.workers.telegram.commands._assign_current_branch_and_confirm", return_value=CONFIRMATION):
            result = await create_branch_choice(update, context)
        
        assert result == CONFIRMATION


class TestBranchSelectHandler:
    @pytest.mark.asyncio
    async def test_create_branch_select_valid_selection(self):
        """Test selecting a valid existing branch."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "1"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        with patch("execqueue.workers.telegram.commands.get_local_branches", return_value=["main", "develop"]):
            result = await create_branch_select(update, context)
        
        assert result == CONFIRMATION
        assert context.user_data["branch"] == "main"
        assert "Zusammenfassung" in update.message.reply_text.call_args[0][0]
        assert update.message.reply_text.call_args.kwargs["reply_markup"] is not None
    
    @pytest.mark.asyncio
    async def test_create_branch_select_invalid_number(self):
        """Test selecting an invalid branch number."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "99"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        with patch("execqueue.workers.telegram.commands.get_local_branches", return_value=["main", "develop"]):
            result = await create_branch_select(update, context)
        
        assert result == BRANCH_SELECT
    
    @pytest.mark.asyncio
    async def test_create_branch_select_cancel(self):
        """Test cancelling branch selection."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "x"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        result = await create_branch_select(update, context)
        
        assert result == BRANCH_CHOICE

    @pytest.mark.asyncio
    async def test_create_branch_select_zero_uses_current_branch(self):
        """Test selecting the active branch fallback."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "0"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}

        with patch("execqueue.workers.telegram.commands.get_current_branch", return_value="develop"):
            result = await create_branch_select(update, context)

        assert result == CONFIRMATION
        assert context.user_data["branch"] == "develop"


class TestBranchNameHandler:
    @pytest.mark.asyncio
    async def test_create_branch_name_valid(self):
        """Test creating a new branch with valid name."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "feature/my-feature"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        with patch("execqueue.workers.telegram.commands.validate_branch_name", return_value=True):
            with patch("execqueue.workers.telegram.commands.create_branch", return_value=(True, "Branch created")):
                result = await create_branch_name(update, context)
        
        assert result == CONFIRMATION
        assert context.user_data["branch"] == "feature/my-feature"
        assert "Zusammenfassung" in update.message.reply_text.call_args[0][0]
        assert update.message.reply_text.call_args.kwargs["reply_markup"] is not None
    
    @pytest.mark.asyncio
    async def test_create_branch_name_invalid(self):
        """Test creating a branch with invalid name."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "invalid branch name"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        with patch("execqueue.workers.telegram.commands.validate_branch_name", return_value=False):
            result = await create_branch_name(update, context)
        
        assert result == BRANCH_NAME
    
    @pytest.mark.asyncio
    async def test_create_branch_name_empty(self):
        """Test creating a branch with empty name."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "   "
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        result = await create_branch_name(update, context)
        
        assert result == BRANCH_NAME
    
    @pytest.mark.asyncio
    async def test_create_branch_name_exists(self):
        """Test creating a branch that already exists."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "main"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        with patch("execqueue.workers.telegram.commands.validate_branch_name", return_value=True):
            with patch("execqueue.workers.telegram.commands.create_branch", return_value=(False, "Branch exists")):
                result = await create_branch_name(update, context)
        
        assert result == BRANCH_NAME


class TestConfirmationHandler:
    @pytest.mark.asyncio
    async def test_create_confirmation_yes(self):
        """Test confirming task creation."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "y"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": "planning",
            "prompt": "Test prompt",
            "title": "Test title",
            "branch": "main",
            "created_by_ref": "123"
        }
        
        with patch("execqueue.workers.telegram.commands.api_client") as mock_client:
            mock_client.create_task = AsyncMock(return_value=(True, "Task created"))
            result = await create_confirmation(update, context)
        
        assert result != CONFIRMATION
        assert context.user_data == {}
    
    @pytest.mark.asyncio
    async def test_create_confirmation_no(self):
        """Test cancelling task creation."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "n"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": "planning"}
        
        result = await create_confirmation(update, context)
        
        assert result != CONFIRMATION
        assert context.user_data == {}
    
    @pytest.mark.asyncio
    async def test_create_confirmation_api_timeout(self):
        """Test handling API timeout during task creation."""
        import httpx
        
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "y"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": "planning",
            "prompt": "Test prompt",
            "created_by_ref": "123"
        }
        
        with patch("execqueue.workers.telegram.commands.api_client") as mock_client:
            mock_client.create_task = AsyncMock(side_effect=httpx.TimeoutException("timeout", request=MagicMock()))
            result = await create_confirmation(update, context)
        
        assert result != CONFIRMATION
        assert context.user_data == {}


class TestCallbackHandlers:
    @pytest.mark.asyncio
    async def test_branch_choice_callback_existing(self):
        """Test branch choice callback for existing branch."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "existing"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}
        
        with patch("execqueue.workers.telegram.commands._show_existing_branches_keyboard", return_value=BRANCH_SELECT):
            result = await branch_choice_callback(update, context)
        
        assert result == BRANCH_SELECT
    
    @pytest.mark.asyncio
    async def test_branch_choice_callback_new(self):
        """Test branch choice callback for new branch."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "new"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}
        
        result = await branch_choice_callback(update, context)
        
        assert result == BRANCH_NAME
    
    @pytest.mark.asyncio
    async def test_branch_select_callback_branch(self):
        """Test branch select callback for branch selection."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "branch:main"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        result = await branch_select_callback(update, context)
        
        assert result == CONFIRMATION
        assert context.user_data["branch"] == "main"
        assert "Zusammenfassung" in update.callback_query.edit_message_text.call_args[0][0]
        assert update.callback_query.edit_message_text.call_args.kwargs["reply_markup"] is not None
    
    @pytest.mark.asyncio
    async def test_branch_select_callback_back(self):
        """Test branch select callback for back navigation."""
        from execqueue.workers.telegram.commands import BRANCH_BACK
        
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = BRANCH_BACK
        update.callback_query.answer = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        with patch("execqueue.workers.telegram.commands._show_branch_choice_keyboard", return_value=BRANCH_CHOICE):
            result = await branch_select_callback(update, context)
        
        assert result == BRANCH_CHOICE
    
    @pytest.mark.asyncio
    async def test_confirm_yes_callback(self):
        """Test confirm_yes callback for yes."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = CONFIRM_YES
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": "planning",
            "prompt": "Test prompt",
            "created_by_ref": "123"
        }
        
        with patch("execqueue.workers.telegram.commands.api_client") as mock_client:
            mock_client.create_task = AsyncMock(return_value=(True, "Task created"))
            result = await confirm_yes(update, context)
        
        assert result != CONFIRMATION
        assert context.user_data == {}
    
    @pytest.mark.asyncio
    async def test_confirm_no_callback(self):
        """Test confirm_no callback for no."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = CONFIRM_NO
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": "planning"}
        
        result = await confirm_no(update, context)
        
        assert result != CONFIRMATION
        assert context.user_data == {}
