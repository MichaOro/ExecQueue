"""Tests for the WriteTaskValidator."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.orm import Session

from execqueue.models.task_execution import TaskExecution
from execqueue.runner.write_task_validator import WriteTaskValidator


@pytest.fixture
def validator() -> WriteTaskValidator:
    """Create a WriteTaskValidator for testing."""
    return WriteTaskValidator()


@pytest.fixture
def mock_execution() -> TaskExecution:
    """Create a mock TaskExecution for testing."""
    execution = MagicMock(spec=TaskExecution)
    execution.id = "test-execution-id"
    execution.task_id = "test-task-id"
    execution.worktree_path = None
    return execution


@pytest.mark.asyncio
async def test_validate_non_write_task(validator: WriteTaskValidator, mock_execution: TaskExecution) -> None:
    """Test validating a non-write task (should pass)."""
    # Mock _is_write_task to return False
    validator._is_write_task = AsyncMock(return_value=False)
    
    result = await validator.validate(mock_execution)
    
    assert result.passed
    assert result.status.value == "passed"
    assert len(result.issues) == 0
    assert result.validator_name == "write_task_validator"


@pytest.mark.asyncio
async def test_validate_missing_worktree_path(validator: WriteTaskValidator, mock_execution: TaskExecution) -> None:
    """Test validating a write task with missing worktree path."""
    # Mock _is_write_task to return True
    validator._is_write_task = AsyncMock(return_value=True)
    mock_execution.worktree_path = None
    
    result = await validator.validate(mock_execution)
    
    assert not result.passed
    assert result.status.value == "failed"
    assert len(result.issues) == 1
    assert result.issues[0].code == "MISSING_WORKTREE_PATH"


@pytest.mark.asyncio
async def test_validate_no_changes(validator: WriteTaskValidator) -> None:
    """Test validating a write task with no changes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir)
        mock_execution = MagicMock(spec=TaskExecution)
        mock_execution.id = "test-execution-id"
        mock_execution.task_id = "test-task-id"
        mock_execution.worktree_path = str(worktree_path)
        
        # Mock _is_write_task to return True
        validator._is_write_task = AsyncMock(return_value=True)
        # Mock _get_changed_files to return empty list
        validator._get_changed_files = AsyncMock(return_value=[])
        
        result = await validator.validate(mock_execution)
        
        assert not result.passed
        assert result.status.value == "failed"
        assert len(result.issues) == 1
        assert result.issues[0].code == "NO_CHANGES"


@pytest.mark.asyncio
async def test_validate_with_changes(validator: WriteTaskValidator) -> None:
    """Test validating a write task with changes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir)
        mock_execution = MagicMock(spec=TaskExecution)
        mock_execution.id = "test-execution-id"
        mock_execution.task_id = "test-task-id"
        mock_execution.worktree_path = str(worktree_path)
        
        # Create a test file
        test_file = worktree_path / "test.py"
        test_file.write_text("print('hello world')")
        
        # Initialize git repo and add file
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "add", "test.py"], cwd=temp_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_dir, capture_output=True)
        
        # Modify the file to create changes
        test_file.write_text("print('hello world updated')")
        
        # Mock _is_write_task to return True
        validator._is_write_task = AsyncMock(return_value=True)
        
        result = await validator.validate(mock_execution)
        
        # Should pass since we have changes and no critical issues
        assert result.status.value in ["passed", "requires_review"]
        # Might have compilation warnings depending on system setup


@pytest.mark.asyncio
async def test_check_file_sizes(validator: WriteTaskValidator) -> None:
    """Test checking file sizes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir)
        
        # Create a large file
        large_file = worktree_path / "large.txt"
        large_file.write_text("x" * (validator.max_file_size_kb * 1024 + 100))  # Just over the limit
        
        # Create a normal file
        normal_file = worktree_path / "normal.txt"
        normal_file.write_text("x" * 100)  # Small file
        
        oversized = await validator._check_file_sizes(worktree_path, ["large.txt", "normal.txt"])
        
        assert len(oversized) == 1
        assert oversized[0][0] == "large.txt"
        assert oversized[0][1] >= validator.max_file_size_kb


@pytest.mark.asyncio
async def test_check_dangerous_patterns(validator: WriteTaskValidator) -> None:
    """Test checking for dangerous patterns."""
    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir)
        
        # Create a file with dangerous patterns
        dangerous_file = worktree_path / "dangerous.py"
        dangerous_file.write_text("""
import os
os.system('rm -rf /')  # Dangerous!
eval('print("evil")')  # Also dangerous
""")
        
        # Create a safe file
        safe_file = worktree_path / "safe.py"
        safe_file.write_text("print('hello world')")
        
        patterns = await validator._check_dangerous_patterns(worktree_path, ["dangerous.py", "safe.py"])
        
        assert "dangerous.py" in patterns
        assert len(patterns["dangerous.py"]) >= 2
        assert "rm -rf /" in patterns["dangerous.py"]
        assert "eval(" in patterns["dangerous.py"]
        assert "safe.py" not in patterns


@pytest.mark.asyncio
async def test_check_python_compilation(validator: WriteTaskValidator) -> None:
    """Test checking Python compilation."""
    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir)
        
        # Create a valid Python file
        valid_file = worktree_path / "valid.py"
        valid_file.write_text("print('hello world')")
        
        # Create an invalid Python file
        invalid_file = worktree_path / "invalid.py"
        invalid_file.write_text("print('hello world'")  # Missing closing parenthesis
        
        # Test valid file
        valid_issues = await validator._check_python_compilation(worktree_path, ["valid.py"])
        assert len(valid_issues) == 0
        
        # Test invalid file
        invalid_issues = await validator._check_python_compilation(worktree_path, ["invalid.py"])
        assert len(invalid_issues) >= 1
        assert invalid_issues[0].code == "PYTHON_SYNTAX_ERROR"


def test_call_count(validator: WriteTaskValidator) -> None:
    """Test that call count is tracked correctly."""
    assert validator.call_count == 0
    
    # This is an async method, so we can't easily call it in a sync test
    # But we can verify the property exists and initializes correctly
    assert hasattr(validator, '_call_count')