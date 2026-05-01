"""Tests for Git helper functions."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from execqueue.workers.telegram.git_helper import (
    GitHelperError,
    GitRepositoryError,
    GitTimeoutError,
    branch_exists,
    create_branch,
    get_local_branches,
    validate_branch_name,
)
from execqueue.workers.telegram.git_writer import create_branch as create_branch_writer


class TestValidateBranchName:
    """Tests for branch name validation."""

    def test_valid_branch_names(self):
        """Test that valid branch names pass validation."""
        valid_names = [
            "main",
            "develop",
            "feature/my-feature",
            "bugfix/123",
            "hotfix_v1.0",
            "release-1.0.0",
            "a",  # Single character is valid
        ]
        for name in valid_names:
            assert validate_branch_name(name) is True, f"Expected {name} to be valid"

    def test_invalid_branch_names_empty(self):
        """Test that empty branch names are rejected."""
        assert validate_branch_name("") is False
        assert validate_branch_name("   ") is False

    def test_invalid_branch_names_whitespace(self):
        """Test that branch names with whitespace are rejected."""
        assert validate_branch_name("my branch") is False
        assert validate_branch_name("branch name") is False

    def test_invalid_branch_names_special_chars(self):
        """Test that branch names with special characters are rejected."""
        invalid_names = [
            "my~branch",
            "my^branch",
            "my:branch",
            "my?branch",
            "my*branch",
            "my[branch]",
            "my\\\\branch",
        ]
        for name in invalid_names:
            assert validate_branch_name(name) is False, f"Expected {name} to be invalid"

    def test_invalid_branch_names_slashes(self):
        """Test that branch names starting/ending with slash are rejected."""
        assert validate_branch_name("/main") is False
        assert validate_branch_name("main/") is False

    def test_invalid_branch_names_dots(self):
        """Test that branch names with double dots are rejected."""
        assert validate_branch_name("my..branch") is False

    def test_invalid_branch_names_dash_start(self):
        """Test that branch names starting with dash are rejected."""
        assert validate_branch_name("-feature") is False

    def test_invalid_branch_names_lock_suffix(self):
        """Test that branch names ending with .lock are rejected."""
        assert validate_branch_name("main.lock") is False
        assert validate_branch_name("feature.lock") is False

    def test_invalid_branch_names_too_long(self):
        """Test that very long branch names are rejected."""
        assert validate_branch_name("a" * 256) is False

    def test_invalid_branch_names_control_chars(self):
        """Test that branch names with control characters are rejected."""
        assert validate_branch_name("my\x00branch") is False
        assert validate_branch_name("my\x1fbranch") is False
        assert validate_branch_name("my\x7fbranch") is False


class TestGetLocalBranches:
    """Tests for get_local_branches function."""

    def test_get_branches_returns_list(self):
        """Test getting branches without touching the real repository."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="* main\n  feature/test\n",
                stderr="",
            )
            branches = get_local_branches()

        assert branches == ["main", "feature/test"]

    def test_get_branches_from_nonexistent_path(self):
        """Test that nonexistent path raises GitRepositoryError."""
        with pytest.raises(GitRepositoryError):
            get_local_branches(repo_path=Path("/nonexistent/path"))

    def test_get_branches_timeout(self):
        """Test that timeout is handled correctly."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git branch", timeout=5)
            with pytest.raises(GitTimeoutError):
                get_local_branches(timeout=1)

    def test_get_branches_parsing(self):
        """Test that branch names are correctly parsed from output."""
        mock_output = "* main\n  develop\n  feature/test\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_output,
                stderr=""
            )
            branches = get_local_branches()
            assert branches == ["main", "develop", "feature/test"]


class TestBranchExists:
    """Tests for branch_exists function."""

    def test_branch_exists_real(self):
        """Test branch existence check via mocked git output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc123\n",
                stderr="",
            )
            assert branch_exists("main") is True

    def test_branch_exists_nonexistent(self):
        """Test checking if a non-existent branch exists."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="fatal: ambiguous argument",
            )
            assert branch_exists("nonexistent-branch-12345") is False

    def test_branch_exists_invalid_name(self):
        """Test that invalid branch names return False."""
        assert branch_exists("invalid name") is False
        assert branch_exists("/invalid") is False

    def test_branch_exists_timeout(self):
        """Test that timeout is handled correctly."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git rev-parse", timeout=5)
            with pytest.raises(GitTimeoutError):
                branch_exists("main", timeout=1)


class TestCreateBranch:
    """Tests for create_branch function."""

    def test_create_branch_success(self):
        """Test successful branch creation."""
        with patch("execqueue.workers.telegram.git_helper.branch_exists", return_value=False):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="",
                    stderr="",
                )
                success, message = create_branch("test-branch-for-validation")

        assert success is True
        assert "erfolgreich erstellt" in message

    def test_create_branch_already_exists(self):
        """Test creating a branch that already exists."""
        with patch("execqueue.workers.telegram.git_helper.branch_exists", return_value=True):
            success, message = create_branch("test-branch-dup-check")

        assert success is False
        assert "existiert" in message

    def test_create_branch_invalid_name(self):
        """Test creating a branch with invalid name."""
        success, message = create_branch("invalid branch name")
        assert success is False
        assert "Ungueltiger Branch-Name" in message

    def test_create_branch_from_nonexistent_path(self):
        """Test creating branch from non-existent path."""
        success, message = create_branch("main", repo_path=Path("/nonexistent"))
        assert success is False
        assert "nicht gefunden" in message

    def test_create_branch_cleanup(self):
        """Test that branch creation reports success without touching git state."""
        branch_name = "test-branch-cleanup"
        with patch("execqueue.workers.telegram.git_helper.branch_exists", side_effect=[False, True]):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="",
                    stderr="",
                )
                success, _ = create_branch(branch_name)
                exists = branch_exists(branch_name)

        assert success is True
        assert exists is True
