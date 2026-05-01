"""Tests for the new Telegram /create conversation handlers (branch selection flow)."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from execqueue.workers.telegram.commands import (
    BRANCH_CHOICE,
    BRANCH_SELECT,
    BRANCH_NAME,
    CONFIRMATION,
    create_branch_choice,
    create_branch_select,
    create_branch_name,
    create_confirmation,
    create_prompt,
)


class MockMessage:
    """Mock Telegram message."""
    def __init__(self, text: str):
        self.text = text
        self.reply_text = AsyncMock()


class MockUpdate:
    """Mock Telegram update."""
    def __init__(self, text: str):
        self.message = MockMessage(text)


class TestCreateBranchChoice:
    """Tests for create_branch_choice handler."""

    @pytest.mark.asyncio
    async def test_select_existing_branch_shows_list(self):
        """Test that selecting existing branch shows branch list."""
        update = MockUpdate("1")
        context = MagicMock()
        context.user_data = {"type": "requirement"}
        
        with patch("execqueue.workers.telegram.commands.get_local_branches") as mock_get:
            mock_get.return_value = ["main", "develop", "feature/test"]
            
            result = await create_branch_choice(update, context)
            
            assert result == BRANCH_SELECT
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_existing_branch_handles_empty_list(self):
        """Test handling when no branches exist."""
        update = MockUpdate("1")
        context = MagicMock()
        context.user_data = {"type": "requirement"}
        
        with patch("execqueue.workers.telegram.commands.get_local_branches") as mock_get:
            mock_get.return_value = []
            
            result = await create_branch_choice(update, context)
            
            assert result == BRANCH_CHOICE

    @pytest.mark.asyncio
    async def test_select_new_branch_prompts_for_name(self):
        """Test that selecting new branch prompts for name."""
        update = MockUpdate("2")
        context = MagicMock()
        context.user_data = {"type": "requirement"}
        
        result = await create_branch_choice(update, context)
        
        assert result == BRANCH_NAME

    @pytest.mark.asyncio
    async def test_invalid_choice_returns_to_branch_choice(self):
        """Test that invalid choice returns to BRANCH_CHOICE state."""
        update = MockUpdate("5")
        context = MagicMock()
        context.user_data = {"type": "requirement"}
        
        result = await create_branch_choice(update, context)
        
        assert result == BRANCH_CHOICE

    @pytest.mark.asyncio
    async def test_handles_none_update(self):
        """Test that None update returns conversation end."""
        result = await create_branch_choice(None, MagicMock())
        
        assert result == -1

    @pytest.mark.asyncio
    async def test_handles_git_error(self):
        """Test handling of Git repository error."""
        update = MockUpdate("1")
        context = MagicMock()
        context.user_data = {"type": "requirement"}
        
        with patch("execqueue.workers.telegram.commands.get_local_branches") as mock_get:
            mock_get.side_effect = Exception("Git error")
            
            result = await create_branch_choice(update, context)
            
            assert result == BRANCH_CHOICE


class TestCreateBranchSelect:
    """Tests for create_branch_select handler."""

    @pytest.mark.asyncio
    async def test_valid_branch_selection(self):
        """Test valid branch number selection."""
        update = MockUpdate("2")
        context = MagicMock()
        context.user_data = {}
        
        with patch("execqueue.workers.telegram.commands.get_local_branches") as mock_get:
            mock_get.return_value = ["main", "develop", "feature/test"]
            
            result = await create_branch_select(update, context)
            
            assert result == CONFIRMATION
            assert context.user_data["branch"] == "develop"
            update.message.reply_text.assert_awaited_once()
            assert "Zusammenfassung" in update.message.reply_text.call_args[0][0]
            assert update.message.reply_text.call_args.kwargs["reply_markup"] is not None

    @pytest.mark.asyncio
    async def test_invalid_number_prompts_again(self):
        """Test that invalid number prompts for retry."""
        update = MockUpdate("99")
        context = MagicMock()
        
        with patch("execqueue.workers.telegram.commands.get_local_branches") as mock_get:
            mock_get.return_value = ["main", "develop"]
            
            result = await create_branch_select(update, context)
            
            assert result == BRANCH_SELECT

    @pytest.mark.asyncio
    async def test_cancel_returns_to_branch_choice(self):
        """Test that 'x' cancels and returns to branch choice."""
        update = MockUpdate("x")
        context = MagicMock()
        
        result = await create_branch_select(update, context)
        
        assert result == BRANCH_CHOICE

    @pytest.mark.asyncio
    async def test_zero_uses_current_active_branch(self):
        """Test that selecting 0 uses the current active branch."""
        update = MockUpdate("0")
        context = MagicMock()
        context.user_data = {}

        with patch("execqueue.workers.telegram.commands.get_current_branch", return_value="develop"):
            result = await create_branch_select(update, context)

            assert result == CONFIRMATION
            assert context.user_data["branch"] == "develop"

    @pytest.mark.asyncio
    async def test_non_numeric_input_prompts_again(self):
        """Test that non-numeric input prompts for retry."""
        update = MockUpdate("invalid")
        context = MagicMock()
        
        result = await create_branch_select(update, context)
        
        assert result == BRANCH_SELECT

    @pytest.mark.asyncio
    async def test_handles_none_update(self):
        """Test that None update returns conversation end."""
        result = await create_branch_select(None, MagicMock())
        
        assert result == -1


class TestCreateBranchName:
    """Tests for create_branch_name handler."""

    @pytest.mark.asyncio
    async def test_valid_branch_name(self):
        """Test valid branch name input."""
        update = MockUpdate("feature/new-feature")
        context = MagicMock()
        context.user_data = {}
        
        with patch("execqueue.workers.telegram.commands.validate_branch_name") as mock_validate:
            mock_validate.return_value = True
            with patch("execqueue.workers.telegram.commands.create_branch", return_value=(True, "Branch created")):
                result = await create_branch_name(update, context)
            
            assert result == CONFIRMATION
            assert context.user_data["branch"] == "feature/new-feature"
            update.message.reply_text.assert_awaited_once()
            assert "Zusammenfassung" in update.message.reply_text.call_args[0][0]
            assert update.message.reply_text.call_args.kwargs["reply_markup"] is not None

    @pytest.mark.asyncio
    async def test_invalid_branch_name_prompts_again(self):
        """Test that invalid branch name prompts for retry."""
        update = MockUpdate("invalid name with spaces")
        context = MagicMock()
        
        with patch("execqueue.workers.telegram.commands.validate_branch_name") as mock_validate:
            mock_validate.return_value = False
            
            result = await create_branch_name(update, context)
            
            assert result == BRANCH_NAME

    @pytest.mark.asyncio
    async def test_empty_name_prompts_again(self):
        """Test that empty name prompts for retry."""
        update = MockUpdate("   ")
        context = MagicMock()
        
        result = await create_branch_name(update, context)
        
        assert result == BRANCH_NAME

    @pytest.mark.asyncio
    async def test_handles_none_update(self):
        """Test that None update returns conversation end."""
        result = await create_branch_name(None, MagicMock())
        
        assert result == -1


class TestCreateConfirmation:
    """Tests for create_confirmation handler."""

    @pytest.mark.asyncio
    async def test_confirm_with_y(self):
        """Test confirmation with 'y'."""
        update = MockUpdate("y")
        context = MagicMock()
        context.user_data = {
            "type": "planning",
            "prompt": "Test prompt",
            "branch": "feature/test",
            "created_by_ref": "telegram:123"
        }
        
        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(return_value=(True, "Task created"))
            
            result = await create_confirmation(update, context)
            
            assert result == -1
            assert context.user_data == {}  # Cleared after success

    @pytest.mark.asyncio
    async def test_confirm_with_ja(self):
        """Test confirmation with 'ja' (German)."""
        update = MockUpdate("ja")
        context = MagicMock()
        context.user_data = {
            "type": "execution",
            "prompt": "Deploy",
            "branch": "main",
            "created_by_ref": "telegram:456"
        }
        
        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(return_value=(True, "Task created"))
            
            result = await create_confirmation(update, context)
            
            assert result == -1

    @pytest.mark.asyncio
    async def test_cancel_with_n(self):
        """Test cancellation with 'n'."""
        update = MockUpdate("n")
        context = MagicMock()
        context.user_data = {"test": "data"}
        
        result = await create_confirmation(update, context)
        
        assert result == -1
        assert context.user_data == {}  # Cleared after cancel

    @pytest.mark.asyncio
    async def test_cancel_with_nein(self):
        """Test cancellation with 'nein' (German)."""
        update = MockUpdate("nein")
        context = MagicMock()
        context.user_data = {"test": "data"}
        
        result = await create_confirmation(update, context)
        
        assert result == -1
        assert context.user_data == {}

    @pytest.mark.asyncio
    async def test_cancel_with_x(self):
        """Test cancellation with 'x'."""
        update = MockUpdate("x")
        context = MagicMock()
        context.user_data = {"test": "data"}
        
        result = await create_confirmation(update, context)
        
        assert result == -1
        assert context.user_data == {}

    @pytest.mark.asyncio
    async def test_invalid_response_shows_summary(self):
        """Test that invalid response shows summary again."""
        update = MockUpdate("maybe")
        context = MagicMock()
        context.user_data = {
            "type": "analysis",
            "prompt": "Analyze logs",
            "branch": "develop"
        }
        
        result = await create_confirmation(update, context)
        
        assert result == CONFIRMATION  # Stay in confirmation state
        assert "Zusammenfassung" in update.message.reply_text.call_args[0][0]
        assert update.message.reply_text.call_args.kwargs["reply_markup"] is not None

    @pytest.mark.asyncio
    async def test_api_error_shows_error_message(self):
        """Test that API error shows error message."""
        update = MockUpdate("y")
        context = MagicMock()
        context.user_data = {
            "type": "planning",
            "prompt": "Test",
            "branch": "main",
            "created_by_ref": "telegram:789"
        }
        
        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(return_value=(False, "API Error"))
            
            result = await create_confirmation(update, context)
            
            assert result == -1

    @pytest.mark.asyncio
    async def test_handles_none_update(self):
        """Test that None update returns conversation end."""
        result = await create_confirmation(None, MagicMock())
        
        assert result == -1


class TestStateConstants:
    """Tests for state constant values."""

    def test_state_constants_have_correct_values(self):
        """Test that state constants have the expected values."""
        assert BRANCH_CHOICE == 4
        assert BRANCH_SELECT == 5
        assert BRANCH_NAME == 6
        assert CONFIRMATION == 7

    def test_states_are_distinct(self):
        """Test that all new states have distinct values."""
        states = [BRANCH_CHOICE, BRANCH_SELECT, BRANCH_NAME, CONFIRMATION]
        assert len(states) == len(set(states))

    def test_states_are_after_existing_states(self):
        """Test that new states come after existing states."""
        from execqueue.workers.telegram.commands import CREATE_PROMPT
        assert BRANCH_CHOICE > CREATE_PROMPT


class TestCreateTaskTypeCallback:
    """Tests for create_task_type_callback (inline keyboard)."""

    @pytest.mark.asyncio
    async def test_planning_type_callback(self):
        """Test planning type selection via callback."""
        from execqueue.workers.telegram.commands import CREATE_PROMPT, TYPE_PLANNING
        
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = TYPE_PLANNING
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        result = await create_task_type_callback(update, context)
        
        assert result == CREATE_PROMPT
        assert context.user_data["type"] == TYPE_PLANNING
        update.callback_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_requirement_type_callback(self):
        """Test requirement type selection shows title input."""
        from execqueue.workers.telegram.commands import CREATE_TITLE, TYPE_REQUIREMENT
        
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = TYPE_REQUIREMENT
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        result = await create_task_type_callback(update, context)
        
        assert result == CREATE_TITLE
        assert context.user_data["type"] == TYPE_REQUIREMENT

    @pytest.mark.asyncio
    async def test_handles_none_update(self):
        """Test that None update returns conversation end."""
        result = await create_task_type_callback(None, MagicMock())
        assert result == -1


class TestBranchChoiceCallback:
    """Tests for branch_choice_callback (inline keyboard)."""

    @pytest.mark.asyncio
    async def test_existing_branch_choice(self):
        """Test existing branch choice calls show_existing_branches."""
        from execqueue.workers.telegram.commands import BRANCH_CHOICE_EXISTING, TYPE_REQUIREMENT
        
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = BRANCH_CHOICE_EXISTING
        update.callback_query.answer = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}
        
        with patch("execqueue.workers.telegram.commands._show_existing_branches_keyboard") as mock_show:
            mock_show.return_value = BRANCH_SELECT
            result = await branch_choice_callback(update, context)
            
            assert result == BRANCH_SELECT
            mock_show.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_branch_choice(self):
        """Test new branch choice returns to BRANCH_NAME state."""
        from execqueue.workers.telegram.commands import BRANCH_CHOICE_NEW, TYPE_REQUIREMENT
        
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = BRANCH_CHOICE_NEW
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}
        
        result = await branch_choice_callback(update, context)
        
        assert result == BRANCH_NAME

    @pytest.mark.asyncio
    async def test_bypasses_for_non_requirement(self):
        """Test that branch choice is bypassed for non-requirement types."""
        from execqueue.workers.telegram.commands import BRANCH_CHOICE_EXISTING, TYPE_PLANNING
        
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = BRANCH_CHOICE_EXISTING
        update.callback_query.answer = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": TYPE_PLANNING}  # Not requirement
        
        with patch("execqueue.workers.telegram.commands._show_existing_branches_keyboard") as mock_show:
            mock_show.return_value = BRANCH_SELECT
            result = await branch_choice_callback(update, context)
            
            assert result == BRANCH_SELECT


class TestBranchSelectCallback:
    """Tests for branch_select_callback (inline keyboard)."""

    @pytest.mark.asyncio
    async def test_select_branch(self):
        """Test branch selection from keyboard."""
        from execqueue.workers.telegram.commands import BRANCH_BACK
        
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "branch:feature/test"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        
        result = await branch_select_callback(update, context)
        
        assert result == CONFIRMATION
        assert context.user_data["branch"] == "feature/test"

    @pytest.mark.asyncio
    async def test_back_button(self):
        """Test back button returns to branch choice."""
        from execqueue.workers.telegram.commands import BRANCH_BACK, BRANCH_CHOICE
        
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = BRANCH_BACK
        update.callback_query.answer = AsyncMock()
        context = MagicMock()
        
        with patch("execqueue.workers.telegram.commands._show_branch_choice_keyboard") as mock_show:
            mock_show.return_value = BRANCH_CHOICE
            result = await branch_select_callback(update, context)
            
            assert result == BRANCH_CHOICE


class TestConfirmYesCallback:
    """Tests for confirm_yes callback (inline keyboard)."""

    @pytest.mark.asyncio
    async def test_confirm_yes(self):
        """Test confirmation with yes."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "confirm_yes"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": "planning",
            "prompt": "test prompt",
            "created_by_ref": "user123",
        }
        
        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(return_value=(True, "Task created"))
            result = await confirm_yes(update, context)
            
            assert result == -1  # ConversationHandler.END
            assert context.user_data == {}

    @pytest.mark.asyncio
    async def test_confirm_no(self):
        """Test confirmation with no (cancel)."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "confirm_no"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"type": "planning"}
        
        result = await confirm_no(update, context)
        
        assert result == -1  # ConversationHandler.END
        assert context.user_data == {}

    @pytest.mark.asyncio
    async def test_api_timeout(self):
        """Test API timeout during task creation."""
        import httpx
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = "confirm_yes"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "type": "planning",
            "prompt": "test",
            "created_by_ref": "user123",
        }
        
        with patch("execqueue.workers.telegram.commands.api_client") as mock_api:
            mock_api.create_task = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            result = await confirm_yes(update, context)
            
            assert result == -1
            # edit_message_text is called twice: first "Erstelle Aufgabe...", then error message
            assert update.callback_query.edit_message_text.call_count == 2


class TestTypeSpecificBranchLogic:
    """Tests for type-specific branch logic."""

    @pytest.mark.asyncio
    async def test_planning_flow_uses_current_branch(self):
        """Test that planning type uses the current branch directly."""
        from execqueue.workers.telegram.commands import TYPE_PLANNING, CONFIRMATION
        
        update = MagicMock()
        update.message = MockMessage("Test prompt")
        context = MagicMock()
        context.user_data = {"type": TYPE_PLANNING}
        
        with patch("execqueue.workers.telegram.commands._assign_current_branch_and_confirm") as mock_show:
            mock_show.return_value = CONFIRMATION
            result = await create_prompt(update, context)
            
            assert result == CONFIRMATION
            mock_show.assert_called_once()

    @pytest.mark.asyncio
    async def test_requirement_flow_with_branch_choice(self):
        """Test that requirement type shows branch choice."""
        from execqueue.workers.telegram.commands import TYPE_REQUIREMENT, BRANCH_CHOICE
        
        update = MagicMock()
        update.message = MockMessage("Test prompt")
        context = MagicMock()
        context.user_data = {"type": TYPE_REQUIREMENT}
        
        with patch("execqueue.workers.telegram.commands._show_branch_choice_text") as mock_show:
            mock_show.return_value = BRANCH_CHOICE
            result = await create_prompt(update, context)
            
            # Should go to BRANCH_CHOICE
            assert result == BRANCH_CHOICE
            mock_show.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_existing_branches_direct_no_branches(self):
        """Test direct branch selection with no branches available."""
        from execqueue.workers.telegram.commands import GitRepositoryError
        
        update = MagicMock()
        update.message = MockMessage("")
        context = MagicMock()
        
        with patch("execqueue.workers.telegram.commands.get_local_branches") as mock_branches:
            mock_branches.side_effect = GitRepositoryError("No repo")
            
            result = await _show_existing_branches_direct(update, context)
            
            # Cannot proceed, end conversation
            assert result == -1


# Import the new callback handler for tests
from execqueue.workers.telegram.commands import (
    create_task_type_callback,
    branch_choice_callback,
    branch_select_callback,
    confirm_yes,
    confirm_no,
    _show_existing_branches_direct,
    _show_branch_choice_text,
    TYPE_PLANNING,
    TYPE_REQUIREMENT,
)
