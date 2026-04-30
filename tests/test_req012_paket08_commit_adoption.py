"""Tests for REQ-012-08 Commit Adoption Zielbranch Validierung."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from execqueue.runner.commit_adopter import AdoptionResult, CommitAdopter


class TestAdoptionResult:
    """Test AdoptionResult data structure."""

    def test_adoption_result_default_values(self):
        """Test default values for adoption result."""
        result = AdoptionResult()

        assert result.success is False
        assert result.adopted_commit_sha is None
        assert result.original_commit_sha is None
        assert result.conflict_detected is False
        assert result.validation_passed is False
        assert result.target_branch_head is None
        assert result.error_message is None
        assert result.needs_review is False

    def test_adoption_result_with_success(self):
        """Test adoption result with successful adoption."""
        result = AdoptionResult(
            success=True,
            original_commit_sha="abc123def456",
            adopted_commit_sha="def456abc123",
            conflict_detected=False,
            validation_passed=True,
            target_branch_head="def456abc123",
        )

        assert result.success is True
        assert result.original_commit_sha == "abc123def456"
        assert result.adopted_commit_sha == "def456abc123"
        assert result.validation_passed is True


class TestCommitAdopterValidation:
    """Test commit adoption validation logic."""

    @pytest.fixture
    def simple_repo(self):
        """Create a simple Git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)

            # Create initial commit
            initial_file = repo_path / "README.md"
            initial_file.write_text("# Initial")
            subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)

            yield repo_path

    def test_detects_dirty_worktree(self, simple_repo):
        """Test detection of dirty worktree."""
        # Make worktree dirty
        readme_file = simple_repo / "README.md"
        readme_file.write_text("# Modified")

        adopter = CommitAdopter(
            target_worktree_path=str(simple_repo),
            target_branch="main",
            task_worktree_path=str(simple_repo),
            task_commit_sha="abc123",
        )

        assert adopter._is_target_branch_clean() is False

    def test_detects_clean_worktree(self, simple_repo):
        """Test detection of clean worktree."""
        adopter = CommitAdopter(
            target_worktree_path=str(simple_repo),
            target_branch="main",
            task_worktree_path=str(simple_repo),
            task_commit_sha="abc123",
        )

        assert adopter._is_target_branch_clean() is True

    def test_gets_current_head(self, simple_repo):
        """Test getting current HEAD."""
        adopter = CommitAdopter(
            target_worktree_path=str(simple_repo),
            target_branch="main",
            task_worktree_path=str(simple_repo),
            task_commit_sha="abc123",
        )

        head = adopter._get_current_target_head()
        assert head is not None
        assert len(head) == 40  # SHA-1 length

    def test_validation_commands_pass(self, simple_repo):
        """Test successful validation commands."""
        adopter = CommitAdopter(
            target_worktree_path=str(simple_repo),
            target_branch="main",
            task_worktree_path=str(simple_repo),
            task_commit_sha="abc123",
            validation_commands=["echo 'test'"],
        )

        assert adopter._run_validation_commands() is True

    def test_validation_commands_fail(self, simple_repo):
        """Test failing validation commands."""
        adopter = CommitAdopter(
            target_worktree_path=str(simple_repo),
            target_branch="main",
            task_worktree_path=str(simple_repo),
            task_commit_sha="abc123",
            validation_commands=["exit 1"],
        )

        assert adopter._run_validation_commands() is False

    def test_no_validation_commands(self, simple_repo):
        """Test no validation commands returns True."""
        adopter = CommitAdopter(
            target_worktree_path=str(simple_repo),
            target_branch="main",
            task_worktree_path=str(simple_repo),
            task_commit_sha="abc123",
        )

        assert adopter._run_validation_commands() is True
