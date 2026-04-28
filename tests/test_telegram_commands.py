"""Tests for Telegram bot command handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execqueue.workers.telegram.commands import (
    CREATE_PROMPT,
    CREATE_TASK_TYPE,
    CREATE_TITLE,
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
    async def test_create_prompt_creates_task(self):
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "Test prompt"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": "planning", "created_by_ref": "123"}

        with patch("execqueue.workers.telegram.commands.api_client") as mock_client:
            mock_client.create_task = AsyncMock(return_value=(True, "Aufgabe #12 wurde erstellt."))
            result = await create_prompt(update, context)

        assert result != CREATE_PROMPT
        mock_client.create_task.assert_called_once_with(
            task_type="planning",
            prompt="Test prompt",
            created_by_ref="123",
            title=None,
        )

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
