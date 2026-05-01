"""Tests for the Telegram Git helper module."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from execqueue.workers.telegram.git_helper import (
    get_current_branch,
    get_local_branches,
    validate_branch_name,
    branch_exists,
    create_branch,
    GitHelperError,
    GitRepositoryError,
    GitTimeoutError,
)


class TestGetLocalBranches:
    """Tests for get_local_branches function."""

    def test_returns_empty_list_when_no_branches(self, tmp_path):
        """Test that empty list is returned when no branches exist."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            result = get_local_branches(tmp_path)
            assert result == []

    def test_parses_single_branch_correctly(self, tmp_path):
        """Test parsing of a single branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="  main\n",
                stderr="",
            )
            result = get_local_branches(tmp_path)
            assert result == ["main"]

    def test_parses_current_branch_with_asterisk(self, tmp_path):
        """Test that current branch marker is removed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="* feature-branch\n  main\n",
                stderr="",
            )
            result = get_local_branches(tmp_path)
            assert result == ["feature-branch", "main"]

    def test_handles_multiple_branches(self, tmp_path):
        """Test parsing of multiple branches."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="* main\n  develop\n  feature/test\n  bugfix-123\n",
                stderr="",
            )
            result = get_local_branches(tmp_path)
            assert result == ["main", "develop", "feature/test", "bugfix-123"]

    def test_raises_repository_error_when_path_not_exists(self):
        """Test that GitRepositoryError is raised for non-existent path."""
        non_existent = Path("/nonexistent/path/12345")
        with pytest.raises(GitRepositoryError):
            get_local_branches(non_existent)

    def test_raises_repository_error_on_git_failure(self, tmp_path):
        """Test that GitRepositoryError is raised when git command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
            )
            with pytest.raises(GitRepositoryError) as exc_info:
                get_local_branches(tmp_path)
            assert "not a git repository" in str(exc_info.value)

    def test_raises_timeout_error_on_timeout(self, tmp_path):
        """Test that GitTimeoutError is raised on timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=5)
            with pytest.raises(GitTimeoutError):
                get_local_branches(tmp_path, timeout=5)

    def test_uses_current_directory_when_path_is_none(self):
        """Test that current directory is used when repo_path is None."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="* main\n",
                stderr="",
            )
            result = get_local_branches()
            assert result == ["main"]
            # Verify cwd was set to current directory
            call_args = mock_run.call_args
            assert call_args.kwargs["cwd"] == Path.cwd()


class TestValidateBranchName:
    """Tests for validate_branch_name function."""

    @pytest.mark.parametrize(
        "valid_name",
        [
            "main",
            "develop",
            "feature/new-feature",
            "bugfix-123",
            "hotfix/v1.0",
            "feature_with_underscores",
            "Feature",
            "v1.0.0",
        ],
    )
    def test_valid_branch_names(self, valid_name):
        """Test that valid branch names return True."""
        assert validate_branch_name(valid_name) is True

    @pytest.mark.parametrize(
        "invalid_name",
        [
            "",  # empty
            " ",  # space only
            "feature name",  # space in name
            "feature~name",  # tilde
            "feature^name",  # caret
            "feature:name",  # colon
            "feature?name",  # question mark
            "feature*name",  # asterisk
            "feature[name",  # opening bracket
            "feature]name",  # closing bracket
            "/starts-with-slash",  # starts with slash
            "ends-with-slash/",  # ends with slash
            "two..dots",  # two consecutive dots
            "ends.lock",  # ends with .lock
            "-starts-with-dash",  # starts with dash
        ],
    )
    def test_invalid_branch_names(self, invalid_name):
        """Test that invalid branch names return False."""
        assert validate_branch_name(invalid_name) is False

    def test_long_branch_name(self):
        """Test that very long branch names are rejected."""
        long_name = "a" * 256
        assert validate_branch_name(long_name) is False

    def test_control_characters(self):
        """Test that branch names with control characters are rejected."""
        assert validate_branch_name("feature\x00name") is False
        assert validate_branch_name("feature\x1fname") is False
        assert validate_branch_name("feature\x7fname") is False


class TestBranchExists:
    """Tests for branch_exists function."""

    def test_returns_true_for_existing_branch(self, tmp_path):
        """Test that True is returned for an existing branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc123",
                stderr="",
            )
            result = branch_exists("main", tmp_path)
            assert result is True

    def test_returns_false_for_nonexistent_branch(self, tmp_path):
        """Test that False is returned for a non-existent branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="fatal: ambiguous argument",
            )
            result = branch_exists("nonexistent", tmp_path)
            assert result is False

    def test_returns_false_for_invalid_branch_name(self, tmp_path):
        """Test that False is returned for invalid branch names."""
        # No subprocess call should be made for invalid names
        with patch("subprocess.run") as mock_run:
            result = branch_exists("invalid/name:with:colons", tmp_path)
            assert result is False
            mock_run.assert_not_called()

    def test_raises_repository_error_when_path_not_exists(self):
        """Test that GitRepositoryError is raised for non-existent path."""
        non_existent = Path("/nonexistent/path/12345")
        with pytest.raises(GitRepositoryError):
            branch_exists("main", non_existent)

    def test_raises_timeout_error_on_timeout(self, tmp_path):
        """Test that GitTimeoutError is raised on timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=5)
            with pytest.raises(GitTimeoutError):
                branch_exists("main", tmp_path, timeout=5)

    def test_uses_current_directory_when_path_is_none(self):
        """Test that current directory is used when repo_path is None."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc123",
                stderr="",
            )
            result = branch_exists("main")
            assert result is True
            call_args = mock_run.call_args
            assert call_args.kwargs["cwd"] == Path.cwd()


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    def test_returns_current_branch_name(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="main\n",
                stderr="",
            )
            result = get_current_branch(tmp_path)
            assert result == "main"

    def test_raises_on_detached_head(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="HEAD\n",
                stderr="",
            )
            with pytest.raises(GitRepositoryError):
                get_current_branch(tmp_path)

    def test_raises_timeout_error_on_timeout(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=5)
            with pytest.raises(GitTimeoutError):
                get_current_branch(tmp_path, timeout=5)


class TestGitHelperExceptions:
    """Tests for Git helper exception hierarchy."""

    def test_git_helper_error_is_exception(self):
        """Test that GitHelperError is a subclass of Exception."""
        assert issubclass(GitHelperError, Exception)

    def test_git_repository_error_is_git_helper_error(self):
        """Test that GitRepositoryError is a subclass of GitHelperError."""
        assert issubclass(GitRepositoryError, GitHelperError)

    def test_git_timeout_error_is_git_helper_error(self):
        """Test that GitTimeoutError is a subclass of GitHelperError."""
        assert issubclass(GitTimeoutError, GitHelperError)

    def test_exceptions_can_be_caught_as_git_helper_error(self):
        """Test that specific exceptions can be caught as GitHelperError."""
        with pytest.raises(GitHelperError):
            raise GitRepositoryError("test error")

        with pytest.raises(GitHelperError):
            raise GitTimeoutError("timeout")


class TestCreateBranch:
    """Tests for create_branch function."""

    def test_create_branch_success(self, tmp_path):
        """Test successful branch creation."""
        import subprocess
        
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        # Create initial commit
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True)

        # Create branch
        success, message = create_branch("test-branch", tmp_path)

        assert success is True
        assert "erfolgreich erstellt" in message
        
        # Verify branch was actually created
        result = subprocess.run(
            ["git", "branch", "--list", "test-branch"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True
        )
        assert "test-branch" in result.stdout

    def test_create_branch_already_exists(self, tmp_path):
        """Test creation of existing branch fails gracefully."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True)

        # Create branch twice
        create_branch("test-branch", tmp_path)
        success, message = create_branch("test-branch", tmp_path)

        assert success is False
        assert "existiert bereits" in message

    def test_create_branch_invalid_name(self, tmp_path):
        """Test creation with invalid name fails."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True)

        success, message = create_branch("invalid branch", tmp_path)

        assert success is False
        assert "Ungueltiger Branch-Name" in message

    def test_create_branch_repository_not_found(self):
        """Test creation with non-existent path."""
        success, message = create_branch("test", Path("/nonexistent/path"))

        assert success is False
        assert "nicht gefunden" in message

    def test_create_branch_with_valid_names(self, tmp_path):
        """Test various valid branch name formats."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True)

        valid_names = [
            "feature/test",
            "bugfix-123",
            "hotfix/v1.0",
            "feature_with_underscores",
        ]
        
        for branch_name in valid_names:
            success, message = create_branch(branch_name, tmp_path)
            assert success is True, f"Failed to create branch: {branch_name}"
