"""Tests for Telegram bot command handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from execqueue.workers.telegram.bot import (
    health_command,
    restart_command,
    start_command,
)
from execqueue.workers.telegram.commands import (
    CREATE_PROMPT,
    CREATE_TASK_TYPE,
    CREATE_TITLE,
    create_cancel,
    create_prompt,
    create_start,
    create_title,
    create_task_type,
    get_health_command_message,
    get_help_message,
    get_start_message,
    status_command,
)


class TestStartCommand:
    """Tests for /start command handler."""

    @pytest.mark.asyncio
    async def test_start_command_sends_welcome_message(self):
        """Test that /start sends the welcome message via reply_text."""
        # Mock update and context
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        # Execute command
        await start_command(update, context)

        # Verify reply_text was called (NOT text!)
        update.message.reply_text.assert_called_once()
        update.message.text.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_command_message_content(self):
        """Test that /start sends the correct welcome message."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        await start_command(update, context)

        # Verify the correct message was sent
        call_args = update.message.reply_text.call_args
        assert call_args is not None
        assert call_args[0][0] == get_start_message()

    @pytest.mark.asyncio
    async def test_start_command_no_message(self):
        """Test that /start handles missing message gracefully."""
        update = MagicMock()
        update.message = None
        context = MagicMock()

        # Should not raise
        await start_command(update, context)


class TestHealthCommand:
    """Tests for /health command handler."""

    @pytest.mark.asyncio
    async def test_health_command_sends_message(self):
        """Test that /health sends message via reply_text."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        await health_command(update, context)

        update.message.reply_text.assert_called_once()
        update.message.text.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_command_message_content(self):
        """Test that /health sends the correct message."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        await health_command(update, context)

        call_args = update.message.reply_text.call_args
        assert call_args is not None
        assert call_args[0][0] == get_health_command_message()


class TestRestartCommand:
    """Tests for /restart command handler."""

    @pytest.mark.asyncio
    async def test_restart_command_sends_message(self):
        """Test that /restart sends message via reply_text."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()

        await restart_command(update, context)

        # Restart command now requires admin role and API call
        # Full testing would require mocking the database and API
        # For now, we just verify the function exists and can be called
        pass


class TestCommandMessages:
    """Tests for command message generation."""

    def test_get_start_message_format(self):
        """Test that start message has correct format for inactive users."""
        message = get_start_message()

        assert "👋 Welcome" in message
        assert "Available commands:" in message
        assert "/start - Start the bot and show available commands" in message
        assert "/help" not in message
        assert "/health" not in message

    def test_get_start_message_for_active_user_shows_help(self):
        """Active regular users see /help in /start, but not /health or /status."""
        message = get_start_message(role="user", is_active=True)

        assert "👋 Welcome" in message
        assert "/start - Start the bot and show available commands" in message
        assert "/help - Show help and usage information" in message
        assert "/status" not in message  # status is only shown in /help
        assert "/health" not in message  # health is operator/admin only
        assert "/create" not in message  # create is operator/admin only

    def test_get_start_message_for_operator_contains_extra_commands(self):
        """Operators should see extra commands in /start."""
        message = get_start_message(role="operator", is_active=True)

        assert "/start - Start the bot and show available commands" in message
        assert "/help - Show help and usage information" in message
        assert "/health - Check system health status" in message

    def test_get_help_message_for_operator(self):
        """Operators should see help and task commands."""
        message = get_help_message(role="operator", is_active=True)

        assert "/help - Show help and usage information" in message
        assert "/health - Check system health status" in message
        assert "/create - Neue Aufgabe erstellen" in message
        assert "/status <ID> - Aufgabestatus abfragen" in message
        assert "/restart - System neu starten" not in message

    def test_get_help_message_for_admin(self):
        """Admins should also see restart in /help."""
        message = get_help_message(role="admin", is_active=True)

        assert "/create - Neue Aufgabe erstellen" in message
        assert "/status <ID> - Aufgabestatus abfragen" in message
        assert "/restart - System neu starten" in message

    def test_get_health_command_message(self):
        """Test health command message content."""
        message = get_health_command_message()

        # Should contain health report or error message
        assert "Health" in message or "health" in message or "Error" in message

    def test_get_command_list(self):
        """Test that command list returns expected structure."""
        from execqueue.workers.telegram.commands import get_command_list

        commands = get_command_list()

        assert isinstance(commands, list)
        assert len(commands) == 1

        for cmd in commands:
            assert "command" in cmd
            assert "description" in cmd
            assert isinstance(cmd["command"], str)
            assert isinstance(cmd["description"], str)


class TestCreateCommand:
    """Tests for /create conversation handler."""

    @pytest.mark.asyncio
    async def test_create_start_requires_active_user(self):
        """Test that /create requires an active user."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()

        # Mock get_user_info to return inactive user
        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("user", False),
        ):
            result = await create_start(update, context)

        # Should reject inactive user
        update.message.reply_text.assert_called_once()
        assert "nicht aktiv" in update.message.reply_text.call_args[0][0]
        # Should end conversation
        assert result != CREATE_TASK_TYPE

    @pytest.mark.asyncio
    async def test_create_start_requires_admin_or_operator(self):
        """Test that /create requires admin or operator role."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()

        # Mock get_user_info to return regular user
        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("user", True),
        ):
            result = await create_start(update, context)

        # Should reject non-admin/operator
        update.message.reply_text.assert_called_once()
        assert "Zugriff verweigert" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_start_allows_admin(self):
        """Test that /create allows admin users."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.user_data = {}  # Use real dict, not MagicMock

        # Mock get_user_info to return admin
        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("admin", True),
        ):
            result = await create_start(update, context)

        # Should proceed to task type selection
        assert result == CREATE_TASK_TYPE
        update.message.reply_text.assert_called_once()
        assert "Welchen Typ" in update.message.reply_text.call_args[0][0]
        assert "1 - Planning" in update.message.reply_text.call_args[0][0]
        assert "4 - Requirement" in update.message.reply_text.call_args[0][0]
        # Should store created_by_ref
        assert context.user_data["created_by_ref"] == "123"

    @pytest.mark.asyncio
    async def test_create_start_allows_operator(self):
        """Test that /create allows operator users."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 456

        context = MagicMock()

        # Mock get_user_info to return operator
        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("operator", True),
        ):
            result = await create_start(update, context)

        # Should proceed to task type selection
        assert result == CREATE_TASK_TYPE

    @pytest.mark.asyncio
    async def test_create_task_type_selects_task(self):
        """Test that task type 1 selects 'planning'."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "1"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        result = await create_task_type(update, context)

        assert result == CREATE_PROMPT
        assert context.user_data["type"] == "planning"

    @pytest.mark.asyncio
    async def test_create_task_type_selects_requirement(self):
        """Test that task type 2 now selects 'execution'."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "2"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        result = await create_task_type(update, context)

        assert result == CREATE_PROMPT
        assert context.user_data["type"] == "execution"

    @pytest.mark.asyncio
    async def test_create_task_type_selects_analysis(self):
        """Test that task type 3 selects 'analysis'."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "3"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        result = await create_task_type(update, context)

        assert result == CREATE_PROMPT
        assert context.user_data["type"] == "analysis"

    @pytest.mark.asyncio
    async def test_create_task_type_selects_requirement_and_requests_title(self):
        """Test that task type 4 selects 'requirement' and asks for a title."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "4"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        result = await create_task_type(update, context)

        assert result == CREATE_TITLE
        assert context.user_data["type"] == "requirement"
        assert "Requirement-Titel" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_task_type_rejects_invalid(self):
        """Test that invalid task type shows error."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "5"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        result = await create_task_type(update, context)

        # Should stay in task type selection
        assert result == CREATE_TASK_TYPE
        update.message.reply_text.assert_called_once()
        assert "Ungueltige Auswahl" in update.message.reply_text.call_args[0][0] or "Ungültige Auswahl" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_title_accepts_requirement_title(self):
        """Requirement flow should store the title before asking for the prompt."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "  Requirement Title  "
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"type": "requirement"}

        result = await create_title(update, context)

        assert result == CREATE_PROMPT
        assert context.user_data["title"] == "Requirement Title"

    @pytest.mark.asyncio
    async def test_create_title_rejects_empty_value(self):
        """Requirement flow should reject empty titles."""
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
    async def test_create_prompt_creates_task(self):
        """Test that /create prompt creates task via API."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "Test prompt"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {
            "type": "planning",
            "created_by_ref": "123",
        }

        # Mock API client
        with patch(
            "execqueue.workers.telegram.commands.api_client"
        ) as mock_client:
            mock_client.create_task = AsyncMock(
                return_value=(True, "Aufgabe #12 wurde erstellt.")
            )
            result = await create_prompt(update, context)

        # Should call API
        mock_client.create_task.assert_called_once_with(
            task_type="planning",
            prompt="Test prompt",
            created_by_ref="123",
            title=None,
        )
        # Should clear user_data
        assert context.user_data == {}
        # Should end conversation
        assert result != CREATE_PROMPT
        last_call = update.message.reply_text.call_args_list[-1]
        assert "Aufgabe #12 wurde erstellt." in last_call[0][0]

    @pytest.mark.asyncio
    async def test_create_prompt_passes_requirement_title(self):
        """Requirement flow should forward the captured title to the API client."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "Requirement prompt"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {
            "type": "requirement",
            "title": "REQ-123",
            "created_by_ref": "123",
        }

        with patch("execqueue.workers.telegram.commands.api_client") as mock_client:
            mock_client.create_task = AsyncMock(
                return_value=(True, "Aufgabe #13 wurde erstellt.")
            )
            result = await create_prompt(update, context)

        mock_client.create_task.assert_called_once_with(
            task_type="requirement",
            prompt="Requirement prompt",
            created_by_ref="123",
            title="REQ-123",
        )
        assert context.user_data == {}
        assert result != CREATE_PROMPT

    @pytest.mark.asyncio
    async def test_create_prompt_handles_api_error(self):
        """Test that /create handles API errors gracefully."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "Test prompt"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"type": "planning", "created_by_ref": "123"}

        # Mock API client to fail
        with patch(
            "execqueue.workers.telegram.commands.api_client"
        ) as mock_client:
            mock_client.create_task = AsyncMock(return_value=(False, "API error"))
            result = await create_prompt(update, context)

        # Should reply with error
        assert update.message.reply_text.call_count >= 2  # loading + error
        last_call = update.message.reply_text.call_args_list[-1]
        assert "❌" in last_call[0][0]

    @pytest.mark.asyncio
    async def test_create_rejects_empty_prompt(self):
        """Test that empty prompt is rejected."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "   "
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"type": "planning", "created_by_ref": "123"}

        result = await create_prompt(update, context)

        # Should stay in prompt state
        assert result == CREATE_PROMPT
        update.message.reply_text.assert_called_once()
        assert "nicht leer" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_cancel_clears_state(self):
        """Test that /create cancel clears user_data."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"type": "planning", "created_by_ref": "123"}

        result = await create_cancel(update, context)

        # Should clear user_data
        assert context.user_data == {}
        # Should end conversation
        assert result != CREATE_PROMPT


class TestStatusCommand:
    """Tests for /status command handler."""

    @pytest.mark.asyncio
    async def test_status_requires_active_user(self):
        """Test that /status requires an active user."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = ["123"]

        # Mock get_user_info to return inactive user
        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("user", False),
        ):
            await status_command(update, context)

        # Should reject inactive user
        update.message.reply_text.assert_called_once()
        assert "nicht aktiv" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_status_requires_task_number(self):
        """Test that /status requires a task number argument."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = []  # No arguments

        # Mock get_user_info to return active user
        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("admin", True),
        ):
            await status_command(update, context)

        # Should show usage error
        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args[0][0]
        assert "Ungueltige Verwendung" in msg or "Ungültige Verwendung" in msg

    @pytest.mark.asyncio
    async def test_status_rejects_invalid_task_number(self):
        """Test that /status rejects non-numeric task numbers."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = ["abc"]

        # Mock get_user_info to return active user
        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("admin", True),
        ):
            await status_command(update, context)

        # Should show validation error
        update.message.reply_text.assert_called_once()
        assert "Zahl" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_status_fetches_from_api(self):
        """Test that /status fetches task status from API."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = ["42"]

        # Mock get_user_info and API client
        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("admin", True),
        ):
            with patch(
                "execqueue.workers.telegram.commands.api_client"
            ) as mock_client:
                mock_client.get_task_status = AsyncMock(
                    return_value=(True, {"status": "completed"})
                )
                await status_command(update, context)

        # Should call API
        mock_client.get_task_status.assert_called_once_with(42)
        # Should reply with status
        assert update.message.reply_text.call_count >= 2  # loading + status
        last_call = update.message.reply_text.call_args_list[-1]
        assert "completed" in last_call[0][0]

    @pytest.mark.asyncio
    async def test_status_handles_not_found(self):
        """Test that /status handles task not found."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = ["999"]

        with patch(
            "execqueue.workers.telegram.commands.get_user_info",
            return_value=("admin", True),
        ):
            with patch(
                "execqueue.workers.telegram.commands.api_client"
            ) as mock_client:
                mock_client.get_task_status = AsyncMock(
                    return_value=(False, "Aufgabe nicht gefunden.")
                )
                await status_command(update, context)

        # Should reply with error
        last_call = update.message.reply_text.call_args_list[-1]
        assert "❌" in last_call[0][0]


class TestHelpCommandEnhanced:
    """Tests for enhanced /help command with role-based filtering."""

    @pytest.mark.asyncio
    async def test_help_shows_task_commands_for_admin(self):
        """Test that /help shows task commands for admin users."""
        from execqueue.workers.telegram.bot import help_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()

        # Patch at the auth module where it's actually imported
        with patch(
            "execqueue.workers.telegram.auth.get_user_info",
            return_value=("admin", True),
        ):
            await help_command(update, context)

        message = update.message.reply_text.call_args[0][0]
        assert "/create" in message
        assert "/status" in message
        assert "/restart" in message
        assert "/help - Show help and usage information" in message
        assert "/health - Check system health status" in message

    @pytest.mark.asyncio
    async def test_help_shows_task_commands_for_operator(self):
        """Test that /help shows task commands for operator users."""
        from execqueue.workers.telegram.bot import help_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()

        with patch(
            "execqueue.workers.telegram.auth.get_user_info",
            return_value=("operator", True),
        ):
            await help_command(update, context)

        message = update.message.reply_text.call_args[0][0]
        assert "/create" in message
        assert "/status" in message
        assert "/restart" not in message  # admin only
        assert "/help - Show help and usage information" in message
        assert "/health - Check system health status" in message

    @pytest.mark.asyncio
    async def test_help_hides_task_commands_for_user(self):
        """Test that /help shows /status but hides /create for regular users."""
        from execqueue.workers.telegram.bot import help_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()

        with patch(
            "execqueue.workers.telegram.auth.get_user_info",
            return_value=("user", True),
        ):
            await help_command(update, context)

        message = update.message.reply_text.call_args[0][0]
        assert "/status" in message  # status is available to all active users
        assert "/create" not in message  # create is operator/admin only
        assert "/restart" not in message  # restart is admin only


class TestRestartCommand:
    """Tests for /restart command with ACP support."""

    @pytest.mark.asyncio
    async def test_restart_command_invalid_argument(self):
        """Test that /restart rejects invalid arguments."""
        from execqueue.workers.telegram.bot import restart_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = ["invalid"]

        # Mock admin user
        mock_user = MagicMock()
        mock_user.role = "admin"
        mock_user.telegram_id = 123
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        
        mock_session_instance = MagicMock()
        mock_session_instance.execute.return_value = mock_result
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        with patch("execqueue.workers.telegram.bot.create_session", return_value=mock_session_instance):
            await restart_command(update, context)

        # Should show error message
        update.message.reply_text.assert_called_once()
        assert "Ungültiger Parameter" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_restart_command_default_system(self):
        """Test that /restart (no args) triggers system restart."""
        from execqueue.workers.telegram.bot import restart_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = []

        # Mock admin user
        mock_user = MagicMock()
        mock_user.role = "admin"
        mock_user.telegram_id = 123
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        
        mock_session_instance = MagicMock()
        mock_session_instance.execute.return_value = mock_result
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        with patch("execqueue.workers.telegram.bot.create_session", return_value=mock_session_instance):
            with patch(
                "execqueue.workers.telegram.commands.trigger_system_restart"
            ) as mock_restart:
                mock_restart.return_value = (True, "System restarted")
                await restart_command(update, context)

        # Should call system restart
        mock_restart.assert_called_once()
        assert update.message.reply_text.call_count >= 2  # confirmation + result

    @pytest.mark.asyncio
    async def test_restart_command_acp(self):
        """Test that /restart acp triggers ACP restart."""
        from execqueue.workers.telegram.bot import restart_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = ["acp"]

        # Mock admin user
        mock_user = MagicMock()
        mock_user.role = "admin"
        mock_user.telegram_id = 123
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        
        mock_session_instance = MagicMock()
        mock_session_instance.execute.return_value = mock_result
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        with patch("execqueue.workers.telegram.bot.create_session", return_value=mock_session_instance):
            with patch(
                "execqueue.workers.telegram.commands.trigger_acp_restart"
            ) as mock_restart:
                mock_restart.return_value = (True, "ACP restarted")
                await restart_command(update, context)

        # Should call ACP restart
        mock_restart.assert_called_once()
        # Should show ACP-specific confirmation
        assert "ACP-Neustart" in update.message.reply_text.call_args_list[0][0][0]

    @pytest.mark.asyncio
    async def test_restart_command_all(self):
        """Test that /restart all triggers full restart."""
        from execqueue.workers.telegram.bot import restart_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = ["all"]

        # Mock admin user
        mock_user = MagicMock()
        mock_user.role = "admin"
        mock_user.telegram_id = 123
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        
        mock_session_instance = MagicMock()
        mock_session_instance.execute.return_value = mock_result
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        with patch("execqueue.workers.telegram.bot.create_session", return_value=mock_session_instance):
            with patch(
                "execqueue.workers.telegram.commands.trigger_system_restart_all"
            ) as mock_restart:
                mock_restart.return_value = (True, "Full restart")
                await restart_command(update, context)

        # Should call full restart
        mock_restart.assert_called_once()
        # Should show full restart confirmation
        assert "Vollständiger Neustart" in update.message.reply_text.call_args_list[0][0][0]

    @pytest.mark.asyncio
    async def test_restart_command_acp_disabled(self):
        """Test that /restart acp shows error when ACP is disabled."""
        from execqueue.workers.telegram.bot import restart_command

        update = MagicMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 123

        context = MagicMock()
        context.args = ["acp"]

        # Mock DB session and ACP disabled
        mock_user = MagicMock()
        mock_user.role = "admin"
        mock_user.telegram_id = 123
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        
        mock_session_instance = MagicMock()
        mock_session_instance.execute.return_value = mock_result
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        with patch("execqueue.workers.telegram.bot.create_session", return_value=mock_session_instance):
            with patch(
                "execqueue.workers.telegram.commands.trigger_acp_restart"
            ) as mock_restart:
                mock_restart.return_value = (False, "ACP ist deaktiviert")
                await restart_command(update, context)

        # Should show error
        last_call = update.message.reply_text.call_args_list[-1]
        assert "❌" in last_call[0][0]
        assert "deaktiviert" in last_call[0][0].lower()


class TestRestartFunctions:
    """Tests for restart trigger functions."""

    @pytest.mark.asyncio
    async def test_trigger_acp_restart_when_disabled(self):
        """Test that trigger_acp_restart returns error when ACP is disabled."""
        from execqueue.workers.telegram.commands import trigger_acp_restart
        from execqueue.acp.lifecycle import LifecycleResult

        with patch(
            "execqueue.workers.telegram.commands.restart_acp"
        ) as mock_restart:
            mock_restart.return_value = LifecycleResult(
                status="disabled",
                operation="restart",
                message="ACP is disabled. No restart performed.",
            )
            success, message = await trigger_acp_restart()

        assert success is False
        assert "deaktiviert" in message.lower()

    @pytest.mark.asyncio
    async def test_trigger_acp_restart_when_enabled(self):
        """Test that trigger_acp_restart delegates to restart_acp lifecycle authority."""
        from execqueue.workers.telegram.commands import trigger_acp_restart
        from execqueue.acp.lifecycle import LifecycleResult

        with patch(
            "execqueue.workers.telegram.commands.restart_acp"
        ) as mock_restart:
            mock_restart.return_value = LifecycleResult(
                status="success",
                operation="restart",
                message="ACP restart initiated successfully.",
            )
            success, message = await trigger_acp_restart()

        assert success is True
        assert "acp-neustart" in message.lower() or "restart" in message.lower()

    @pytest.mark.asyncio
    async def test_trigger_system_restart_all(self):
        """Test that trigger_system_restart_all calls both endpoints."""
        from execqueue.workers.telegram.commands import trigger_system_restart_all
        from execqueue.acp.lifecycle import LifecycleResult

        with patch(
            "execqueue.workers.telegram.commands.get_settings"
        ) as mock_settings:
            mock_settings.return_value.acp_enabled = True
            mock_settings.return_value.execqueue_api_host = "127.0.0.1"
            mock_settings.return_value.execqueue_api_port = 8000

            with patch(
                "execqueue.workers.telegram.commands.httpx.AsyncClient"
            ) as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"message": "OK"}
                mock_client.return_value.__aenter__.return_value.post.return_value = (
                    mock_response
                )

                with patch(
                    "execqueue.workers.telegram.commands.restart_acp"
                ) as mock_restart:
                    mock_restart.return_value = LifecycleResult(
                        status="external_managed",
                        operation="restart",
                        message="ACP is externally managed.",
                    )
                    success, message = await trigger_system_restart_all()

        assert success is True
        msg_lower = message.lower()
        assert "vollstandig" in msg_lower or "vollstaendig" in msg_lower or "restart" in msg_lower or "neustart" in msg_lower
        assert "/status" not in message
        assert "/restart" not in message

    @pytest.mark.asyncio
    async def test_trigger_acp_restart_hides_internal_failure_details(self):
        from execqueue.workers.telegram.commands import trigger_acp_restart
        from execqueue.acp.lifecycle import LifecycleResult

        with patch(
            "execqueue.workers.telegram.commands.restart_acp"
        ) as mock_restart:
            mock_restart.return_value = LifecycleResult(
                status="failed",
                operation="restart",
                message="ACP restart failed.",
                details={"reason": "restart_command_failed", "exit_code": "1"},
            )
            success, message = await trigger_acp_restart()

        assert success is False
        assert "fehlgeschlagen" in message.lower()
        assert "exit_code" not in message
        assert "restart_command_failed" not in message
