"""Tests for CommitAdopter (REQ-021 Section 5 / REQ-012-08).

Tests for commit adoption logic including cherry-pick, conflict detection,
validation commands, and lifecycle management.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.runner.commit_adopter import (
    AdoptionResult,
    CommitAdopter,
    adopt_commit,
    adopt_commit_with_lifecycle,
)


class TestAdoptionResult:
    """Test AdoptionResult dataclass."""

    def test_defaults(self):
        """Test default values."""
        result = AdoptionResult()
        assert result.success is False
        assert result.adopted_commit_sha is None
        assert result.original_commit_sha is None
        assert result.conflict_detected is False
        assert result.validation_passed is False
        assert result.target_branch_head is None
        assert result.error_message is None
        assert result.needs_review is False

    def test_success_result(self):
        """Test a success result."""
        result = AdoptionResult(
            success=True,
            adopted_commit_sha="abc123",
            original_commit_sha="def456",
            validation_passed=True,
            target_branch_head="ghi789",
        )
        assert result.success is True
        assert result.adopted_commit_sha == "abc123"
        assert result.original_commit_sha == "def456"
        assert result.validation_passed is True
        assert result.target_branch_head == "ghi789"

    def test_conflict_result(self):
        """Test a conflict result."""
        result = AdoptionResult(
            success=False,
            conflict_detected=True,
            error_message="Cherry-pick conflict detected",
            needs_review=True,
        )
        assert result.success is False
        assert result.conflict_detected is True
        assert result.needs_review is True
        assert "conflict" in result.error_message


class TestCommitAdopter:
    """Test CommitAdopter functionality."""

    @pytest.fixture
    def adopter(self):
        """Create a CommitAdopter instance."""
        return CommitAdopter(
            target_worktree_path="/tmp/target",
            target_branch="main",
            task_worktree_path="/tmp/task",
            task_commit_sha="abc123def456",
        )

    def test_init(self, adopter):
        """Test CommitAdopter initialization."""
        assert str(adopter.target_worktree_path) == "/tmp/target"
        assert adopter.target_branch == "main"
        assert str(adopter.task_worktree_path) == "/tmp/task"
        assert adopter.task_commit_sha == "abc123def456"
        assert adopter.validation_commands == []

    def test_init_with_validation_commands(self):
        """Test initialization with validation commands."""
        adopter = CommitAdopter(
            target_worktree_path="/tmp/target",
            target_branch="main",
            task_worktree_path="/tmp/task",
            task_commit_sha="abc123",
            validation_commands=["pytest", "ruff check"],
        )
        assert adopter.validation_commands == ["pytest", "ruff check"]

    def test_run_git_command_success(self, adopter):
        """Test running a git command successfully."""
        with patch("execqueue.runner.commit_adopter.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "abc123\n"
            mock_run.return_value = mock_result

            result = adopter._run_git_command(
                ["rev-parse", "HEAD"],
                check=True,
            )

            assert result.returncode == 0
            assert result.stdout == "abc123\n"
            mock_run.assert_called_once()

    def test_run_git_command_failure(self, adopter):
        """Test running a git command that fails."""
        with patch("execqueue.runner.commit_adopter.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "fatal: not a git repository"
            mock_run.return_value = mock_result

            result = adopter._run_git_command(
                ["rev-parse", "HEAD"],
                check=False,
            )

            assert result.returncode == 1

    def test_is_target_branch_clean_true(self, adopter):
        """Test checking if target branch is clean (True)."""
        with patch.object(adopter, "_run_git_command") as mock_cmd:
            mock_result = MagicMock()
            mock_result.stdout = ""
            mock_cmd.return_value = mock_result

            is_clean = adopter._is_target_branch_clean()
            assert is_clean is True

    def test_is_target_branch_clean_false(self, adopter):
        """Test checking if target branch is clean (False)."""
        with patch.object(adopter, "_run_git_command") as mock_cmd:
            mock_result = MagicMock()
            mock_result.stdout = "M modified_file.txt"
            mock_cmd.return_value = mock_result

            is_clean = adopter._is_target_branch_clean()
            assert is_clean is False

    def test_get_current_target_head(self, adopter):
        """Test getting current target HEAD."""
        with patch.object(adopter, "_run_git_command") as mock_cmd:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "abc123def456\n"
            mock_cmd.return_value = mock_result

            head = adopter._get_current_target_head()
            assert head == "abc123def456"

    def test_get_current_target_head_failure(self, adopter):
        """Test getting current target HEAD on failure."""
        with patch.object(adopter, "_run_git_command") as mock_cmd:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_cmd.return_value = mock_result

            head = adopter._get_current_target_head()
            assert head is None

    def test_is_commit_already_adopted_true(self, adopter):
        """Test checking if commit is already adopted (True)."""
        with patch.object(adopter, "_run_git_command") as mock_cmd:
            # First call: merge-base returns 0 (ancestor)
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_cmd.return_value = mock_result

            is_adopted = adopter._is_commit_already_adopted()
            assert is_adopted is True

    def test_is_commit_already_adopted_false(self, adopter):
        """Test checking if commit is not yet adopted (False)."""
        with patch.object(adopter, "_run_git_command") as mock_cmd:
            # First call: merge-base returns non-zero (not ancestor)
            # Second call: log doesn't contain SHA
            mock_result1 = MagicMock()
            mock_result1.returncode = 1
            mock_result2 = MagicMock()
            mock_result2.returncode = 0
            mock_result2.stdout = "some other commit log"
            mock_cmd.side_effect = [mock_result1, mock_result2]

            is_adopted = adopter._is_commit_already_adopted()
            assert is_adopted is False

    def test_adopt_dirty_target_worktree(self, adopter):
        """Test adoption fails when target worktree is dirty."""
        with patch.object(adopter, "_is_target_branch_clean", return_value=False):
            result = adopter.adopt()

            assert result.success is False
            assert result.needs_review is True
            assert "uncommitted changes" in result.error_message

    def test_adopt_already_adopted(self, adopter):
        """Test adoption skips when commit already adopted."""
        with patch.object(adopter, "_is_target_branch_clean", return_value=True):
            with patch.object(adopter, "_is_commit_already_adopted", return_value=True):
                with patch.object(adopter, "_get_current_target_head", return_value="existing_head"):
                    result = adopter.adopt()

                    assert result.success is True
                    assert result.adopted_commit_sha == adopter.task_commit_sha
                    assert result.validation_passed is True

    def test_adopt_checkout_failure(self, adopter):
        """Test adoption fails when checkout fails."""
        with patch.object(adopter, "_is_target_branch_clean", return_value=True):
            with patch.object(adopter, "_is_commit_already_adopted", return_value=False):
                with patch.object(adopter, "_checkout_target_branch", return_value=False):
                    result = adopter.adopt()

                    assert result.success is False
                    assert result.needs_review is True
                    assert "checkout" in result.error_message.lower()

    def test_adopt_cherry_pick_conflict(self, adopter):
        """Test adoption detects cherry-pick conflict."""
        with patch.object(adopter, "_is_target_branch_clean", return_value=True):
            with patch.object(adopter, "_is_commit_already_adopted", return_value=False):
                with patch.object(adopter, "_checkout_target_branch", return_value=True):
                    with patch.object(adopter, "_get_current_target_head", return_value="head_before"):
                        with patch.object(adopter, "_run_git_command") as mock_cmd:
                            # Cherry-pick fails with conflict
                            cherry_pick_result = MagicMock()
                            cherry_pick_result.returncode = 1
                            cherry_pick_result.stderr = "error: could not apply... conflict"

                            # Status shows conflict
                            status_result = MagicMock()
                            status_result.stdout = "UU conflicted_file.txt"
                            status_result.returncode = 0

                            # Abort succeeds
                            abort_result = MagicMock()
                            abort_result.returncode = 0

                            mock_cmd.side_effect = [
                                cherry_pick_result,  # cherry-pick
                                status_result,       # status
                                abort_result,        # cherry-pick --abort
                            ]

                            result = adopter.adopt()

                            assert result.success is False
                            assert result.conflict_detected is True
                            assert result.needs_review is True

    def test_adopt_success(self, adopter):
        """Test successful adoption."""
        with patch.object(adopter, "_is_target_branch_clean", return_value=True):
            with patch.object(adopter, "_is_commit_already_adopted", return_value=False):
                with patch.object(adopter, "_checkout_target_branch", return_value=True):
                    with patch.object(adopter, "_get_current_target_head") as mock_head:
                        # First call: head_before, Second call: adopted_sha
                        mock_head.side_effect = ["head_before", "adopted_sha"]

                        with patch.object(adopter, "_run_git_command") as mock_cmd:
                            cherry_pick_result = MagicMock()
                            cherry_pick_result.returncode = 0
                            mock_cmd.return_value = cherry_pick_result

                            result = adopter.adopt()

                            assert result.success is True
                            assert result.adopted_commit_sha == "adopted_sha"
                            assert result.validation_passed is True
                            assert result.target_branch_head == "adopted_sha"

    def test_adopt_with_validation_commands(self):
        """Test adoption with validation commands."""
        adopter = CommitAdopter(
            target_worktree_path="/tmp/target",
            target_branch="main",
            task_worktree_path="/tmp/task",
            task_commit_sha="abc123",
            validation_commands=["pytest"],
        )

        with patch.object(adopter, "_is_target_branch_clean", return_value=True):
            with patch.object(adopter, "_is_commit_already_adopted", return_value=False):
                with patch.object(adopter, "_checkout_target_branch", return_value=True):
                    with patch.object(adopter, "_get_current_target_head") as mock_head:
                        mock_head.side_effect = ["head_before", "adopted_sha"]

                        with patch.object(adopter, "_run_git_command") as mock_cmd:
                            cherry_pick_result = MagicMock()
                            cherry_pick_result.returncode = 0
                            mock_cmd.return_value = cherry_pick_result

                            with patch.object(adopter, "_run_validation_commands", return_value=True):
                                result = adopter.adopt()

                                assert result.success is True
                                assert result.validation_passed is True

    def test_adopt_validation_commands_fail(self):
        """Test adoption when validation commands fail."""
        adopter = CommitAdopter(
            target_worktree_path="/tmp/target",
            target_branch="main",
            task_worktree_path="/tmp/task",
            task_commit_sha="abc123",
            validation_commands=["pytest"],
        )

        with patch.object(adopter, "_is_target_branch_clean", return_value=True):
            with patch.object(adopter, "_is_commit_already_adopted", return_value=False):
                with patch.object(adopter, "_checkout_target_branch", return_value=True):
                    with patch.object(adopter, "_get_current_target_head") as mock_head:
                        mock_head.side_effect = ["head_before", "adopted_sha"]

                        with patch.object(adopter, "_run_git_command") as mock_cmd:
                            cherry_pick_result = MagicMock()
                            cherry_pick_result.returncode = 0
                            mock_cmd.return_value = cherry_pick_result

                            with patch.object(adopter, "_run_validation_commands", return_value=False):
                                result = adopter.adopt()

                                assert result.success is False
                                assert result.validation_passed is False
                                assert result.needs_review is True
                                assert "Validation commands failed" in result.error_message


class TestAdoptCommitFunctions:
    """Test convenience functions for commit adoption."""

    @pytest.mark.asyncio
    async def test_adopt_commit(self):
        """Test adopt_commit convenience function."""
        with patch("execqueue.runner.commit_adopter.CommitAdopter") as mock_adopter_class:
            mock_instance = MagicMock()
            mock_instance.adopt.return_value = AdoptionResult(
                success=True,
                adopted_commit_sha="abc123",
            )
            mock_adopter_class.return_value = mock_instance

            result = await adopt_commit(
                target_worktree_path="/tmp/target",
                target_branch="main",
                task_worktree_path="/tmp/task",
                task_commit_sha="abc123",
            )

            assert result.success is True
            assert result.adopted_commit_sha == "abc123"
            mock_adopter_class.assert_called_once_with(
                target_worktree_path="/tmp/target",
                target_branch="main",
                task_worktree_path="/tmp/task",
                task_commit_sha="abc123",
                validation_commands=None,
            )

    @pytest.mark.asyncio
    async def test_adopt_commit_with_lifecycle_success(self):
        """Test adopt_commit_with_lifecycle with successful adoption."""
        session = MagicMock()
        execution = TaskExecution(
            id=uuid4(),
            task_id=uuid4(),
            runner_id="test-runner",
            status=ExecutionStatus.RESULT_INSPECTION.value,
            commit_sha_after="abc123def456",
            worktree_path="/tmp/task",
        )

        with patch("execqueue.runner.commit_adopter.CommitAdopter") as mock_adopter_class:
            mock_instance = MagicMock()
            mock_instance.adopt.return_value = AdoptionResult(
                success=True,
                adopted_commit_sha="adopted_sha",
                validation_passed=True,
            )
            mock_adopter_class.return_value = mock_instance

            result = await adopt_commit_with_lifecycle(
                session=session,
                execution=execution,
                target_worktree_path="/tmp/target",
                target_branch="main",
            )

            assert result.success is True
            assert result.adopted_commit_sha == "adopted_sha"
            assert execution.status == ExecutionStatus.DONE.value
            assert execution.adoption_status == "success"
            assert execution.adoption_error is None
            session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_adopt_commit_with_lifecycle_no_sha(self):
        """Test adopt_commit_with_lifecycle with no commit SHA."""
        session = MagicMock()
        execution = TaskExecution(
            id=uuid4(),
            task_id=uuid4(),
            runner_id="test-runner",
            status=ExecutionStatus.RESULT_INSPECTION.value,
            commit_sha_after=None,
        )

        result = await adopt_commit_with_lifecycle(
            session=session,
            execution=execution,
            target_worktree_path="/tmp/target",
            target_branch="main",
        )

        assert result.success is False
        assert "No commit SHA" in result.error_message
        assert execution.adoption_status == "failed"
        session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_adopt_commit_with_lifecycle_conflict(self):
        """Test adopt_commit_with_lifecycle with conflict."""
        session = MagicMock()
        execution = TaskExecution(
            id=uuid4(),
            task_id=uuid4(),
            runner_id="test-runner",
            status=ExecutionStatus.RESULT_INSPECTION.value,
            commit_sha_after="abc123def456",
            worktree_path="/tmp/task",
        )

        with patch("execqueue.runner.commit_adopter.CommitAdopter") as mock_adopter_class:
            mock_instance = MagicMock()
            mock_instance.adopt.return_value = AdoptionResult(
                success=False,
                conflict_detected=True,
                needs_review=True,
                error_message="Cherry-pick conflict",
            )
            mock_adopter_class.return_value = mock_instance

            result = await adopt_commit_with_lifecycle(
                session=session,
                execution=execution,
                target_worktree_path="/tmp/target",
                target_branch="main",
            )

            assert result.success is False
            assert result.conflict_detected is True
            assert execution.status == ExecutionStatus.REVIEW.value
            assert execution.adoption_status == "review"
            session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_adopt_commit_with_lifecycle_failure(self):
        """Test adopt_commit_with_lifecycle with adoption failure."""
        session = MagicMock()
        execution = TaskExecution(
            id=uuid4(),
            task_id=uuid4(),
            runner_id="test-runner",
            status=ExecutionStatus.RESULT_INSPECTION.value,
            commit_sha_after="abc123def456",
            worktree_path="/tmp/task",
        )

        with patch("execqueue.runner.commit_adopter.CommitAdopter") as mock_adopter_class:
            mock_instance = MagicMock()
            mock_instance.adopt.return_value = AdoptionResult(
                success=False,
                conflict_detected=False,
                needs_review=False,
                error_message="Adoption failed",
            )
            mock_adopter_class.return_value = mock_instance

            result = await adopt_commit_with_lifecycle(
                session=session,
                execution=execution,
                target_worktree_path="/tmp/target",
                target_branch="main",
            )

            assert result.success is False
            assert execution.status == ExecutionStatus.FAILED.value
            assert execution.adoption_status == "failed"
            assert execution.adoption_error == "Adoption failed"
            session.commit.assert_called()