"""Tests for REQ-012-07 Result Inspection Task Worktree.

This module tests:
- Git state detection (commits, changed files, uncommitted changes)
- Path validation against allowed paths
- Read-only violation detection
- Inspection result metadata
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from execqueue.orchestrator.models import RunnerMode
from execqueue.runner.result_inspector import (
    ResultInspector,
    InspectionResult,
    inspect_task_result,
)


class TestInspectionResult:
    """Test InspectionResult data structure."""

    def test_inspection_result_default_values(self):
        """Test default values for inspection result."""
        result = InspectionResult()

        assert result.commit_sha_after is None
        assert result.new_commit_shas is None
        assert result.changed_files is None
        assert result.diff_stat is None
        assert result.has_uncommitted_changes is False
        assert result.inspection_status == "passed"
        assert result.read_only_violation is False
        assert result.out_of_scope_changes is False
        assert result.violation_details is None

    def test_inspection_result_with_values(self):
        """Test inspection result with populated values."""
        result = InspectionResult(
            commit_sha_after="abc123",
            new_commit_shas=["abc123", "def456"],
            changed_files=["file1.py", "file2.py"],
            diff_stat="2 files changed, 10 insertions(+), 5 deletions(-)",
            has_uncommitted_changes=True,
            inspection_status="review",
            read_only_violation=False,
            out_of_scope_changes=False,
        )

        assert result.commit_sha_after == "abc123"
        assert len(result.new_commit_shas) == 2
        assert "file1.py" in result.changed_files
        assert result.has_uncommitted_changes is True
        assert result.inspection_status == "review"


class TestResultInspectorGitDetection:
    """Test Git state detection."""

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary Git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create initial commit
            initial_file = repo_path / "README.md"
            initial_file.write_text("# Initial")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)

            # Get initial commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            initial_sha = result.stdout.strip()

            yield repo_path, initial_sha

    def test_detects_current_commit(self, temp_git_repo):
        """Test detection of current commit."""
        repo_path, initial_sha = temp_git_repo

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.WRITE,
        )

        result = inspector.inspect()

        assert result.commit_sha_after is not None
        assert len(result.commit_sha_after) == 40  # SHA-1 length

    def test_detects_new_commits(self, temp_git_repo):
        """Test detection of new commits."""
        repo_path, initial_sha = temp_git_repo

        # Create a new commit
        new_file = repo_path / "new_file.py"
        new_file.write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "New file"], cwd=repo_path, check=True, capture_output=True)

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.WRITE,
        )

        result = inspector.inspect()

        assert result.new_commit_shas is not None
        assert len(result.new_commit_shas) == 1

    def test_detects_changed_files(self, temp_git_repo):
        """Test detection of changed files."""
        repo_path, initial_sha = temp_git_repo

        # Create and commit a new file
        new_file = repo_path / "new_file.py"
        new_file.write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "New file"], cwd=repo_path, check=True, capture_output=True)

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.WRITE,
        )

        result = inspector.inspect()

        assert result.changed_files is not None
        assert "new_file.py" in result.changed_files

    def test_detects_uncommitted_changes(self, temp_git_repo):
        """Test detection of uncommitted changes."""
        repo_path, initial_sha = temp_git_repo

        # Create uncommitted change
        modified_file = repo_path / "README.md"
        modified_file.write_text("# Modified")

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.WRITE,
        )

        result = inspector.inspect()

        assert result.has_uncommitted_changes is True

    def test_detects_diff_stat(self, temp_git_repo):
        """Test diff stat detection."""
        repo_path, initial_sha = temp_git_repo

        # Create and commit a new file
        new_file = repo_path / "new_file.py"
        new_file.write_text("print('hello')\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "New file"], cwd=repo_path, check=True, capture_output=True)

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.WRITE,
        )

        result = inspector.inspect()

        assert result.diff_stat is not None
        assert "new_file.py" in result.diff_stat


class TestReadonlyViolationDetection:
    """Test read-only violation detection."""

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary Git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create initial commit
            initial_file = repo_path / "README.md"
            initial_file.write_text("# Initial")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            initial_sha = result.stdout.strip()

            yield repo_path, initial_sha

    def test_readonly_violation_on_committed_changes(self, temp_git_repo):
        """Test read-only violation detection for committed changes."""
        repo_path, initial_sha = temp_git_repo

        # Create and commit a change
        new_file = repo_path / "new_file.py"
        new_file.write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "New file"], cwd=repo_path, check=True, capture_output=True)

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.READ_ONLY,
        )

        result = inspector.inspect()

        assert result.read_only_violation is True
        assert result.inspection_status == "failed"
        assert "Read-only task has changes" in result.violation_details["reason"]

    def test_readonly_violation_on_uncommitted_changes(self, temp_git_repo):
        """Test read-only violation detection for uncommitted changes."""
        repo_path, initial_sha = temp_git_repo

        # Create uncommitted change
        modified_file = repo_path / "README.md"
        modified_file.write_text("# Modified")

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.READ_ONLY,
        )

        result = inspector.inspect()

        assert result.read_only_violation is True
        assert result.inspection_status == "failed"

    def test_readonly_no_violation_when_clean(self, temp_git_repo):
        """Test no read-only violation when no changes."""
        repo_path, initial_sha = temp_git_repo

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.READ_ONLY,
        )

        result = inspector.inspect()

        assert result.read_only_violation is False
        assert result.inspection_status == "passed"


class TestPathValidation:
    """Test path validation against allowed paths."""

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary Git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create initial commit
            initial_file = repo_path / "README.md"
            initial_file.write_text("# Initial")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            initial_sha = result.stdout.strip()

            yield repo_path, initial_sha

    def test_out_of_scope_changes_detected(self, temp_git_repo):
        """Test detection of out-of-scope changes."""
        repo_path, initial_sha = temp_git_repo

        # Create file outside allowed scope
        outside_file = repo_path / "outside.py"
        outside_file.write_text("print('outside')")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Outside file"], cwd=repo_path, check=True, capture_output=True)

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.WRITE,
            allowed_paths=["src/"],  # Only allow src/
        )

        result = inspector.inspect()

        assert result.out_of_scope_changes is True
        assert "outside.py" in result.violation_details["out_of_scope_files"]

    def test_in_scope_changes_allowed(self, temp_git_repo):
        """Test that in-scope changes are allowed."""
        repo_path, initial_sha = temp_git_repo

        # Create src directory and file
        src_dir = repo_path / "src"
        src_dir.mkdir()
        inside_file = src_dir / "inside.py"
        inside_file.write_text("print('inside')")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Inside file"], cwd=repo_path, check=True, capture_output=True)

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.WRITE,
            allowed_paths=["src/"],
        )

        result = inspector.inspect()

        assert result.out_of_scope_changes is False
        assert result.inspection_status == "passed"

    def test_no_path_restrictions_when_empty(self, temp_git_repo):
        """Test no restrictions when allowed_paths is empty."""
        repo_path, initial_sha = temp_git_repo

        # Create file anywhere
        any_file = repo_path / "anywhere.py"
        any_file.write_text("print('anywhere')")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Anywhere file"], cwd=repo_path, check=True, capture_output=True)

        inspector = ResultInspector(
            worktree_path=str(repo_path),
            commit_sha_before=initial_sha,
            runner_mode=RunnerMode.WRITE,
            allowed_paths=[],  # No restrictions
        )

        result = inspector.inspect()

        assert result.out_of_scope_changes is False


class TestInspectTaskResult:
    """Test convenience function."""

    @pytest.mark.anyio
    async def test_inspect_task_result_function(self):
        """Test the convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create initial commit
            initial_file = repo_path / "README.md"
            initial_file.write_text("# Initial")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            initial_sha = result.stdout.strip()

            # Use convenience function
            inspection_result = await inspect_task_result(
                worktree_path=str(repo_path),
                commit_sha_before=initial_sha,
                runner_mode=RunnerMode.WRITE,
                allowed_paths=["src/"],
            )

            assert isinstance(inspection_result, InspectionResult)
            assert inspection_result.commit_sha_after is not None
