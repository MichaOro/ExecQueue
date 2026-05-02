"""Tests for GitWorktreeManager (REQ-021 Section 3)."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from execqueue.db.models import WorktreeMetadata, WorktreeStatus
from execqueue.runner.worktree_manager import (
    GitWorktreeManager,
    WorktreeMetadataResult,
)


class TestGitWorktreeManager:
    """Test GitWorktreeManager functionality."""

    @pytest.fixture
    def worktree_manager(self):
        """Create a GitWorktreeManager instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield GitWorktreeManager(worktree_root=tmpdir)

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock(spec=Session)

    def test_init(self, worktree_manager):
        """Test GitWorktreeManager initialization."""
        assert worktree_manager.worktree_root.exists()
        assert worktree_manager.branch_prefix == "task"
        assert worktree_manager.max_concurrent == 10

    def test_generate_worktree_path(self, worktree_manager):
        """Test worktree path generation."""
        workflow_id = uuid4()
        task_id = uuid4()
        
        path = worktree_manager._generate_worktree_path(workflow_id, task_id)
        
        assert path.parent == worktree_manager.worktree_root
        assert path.name.startswith("task_")
        assert str(workflow_id)[:8] in str(path)
        assert str(task_id)[:8] in str(path)

    def test_generate_branch_name(self, worktree_manager):
        """Test branch name generation."""
        workflow_id = uuid4()
        task_id = uuid4()
        
        branch_name = worktree_manager._generate_branch_name(workflow_id, task_id, "main")
        
        assert branch_name.startswith("task/")
        assert "main" in branch_name
        assert str(task_id)[:8] in branch_name

    @pytest.mark.asyncio
    async def test_create_or_get_worktree_new(self, worktree_manager, mock_session):
        """Test creating a new worktree metadata."""
        workflow_id = uuid4()
        task_id = uuid4()
        
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Mock database query to return no existing worktree
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = None
            mock_query.filter.return_value.count.return_value = 0
            mock_session.query.return_value = mock_query
            
            # Mock db commit and refresh
            mock_session.commit = MagicMock()
            mock_session.refresh = MagicMock()
            
            # Pass None for session to trigger get_db_session
            result = await worktree_manager.create_or_get_worktree(
                workflow_id=workflow_id,
                task_id=task_id,
                base_branch="main",
                session=None,
            )
            
            assert isinstance(result, WorktreeMetadataResult)
            assert result.was_created is True
            assert result.metadata is not None
            assert result.error_message is None
            assert result.metadata.workflow_id == workflow_id
            assert result.metadata.task_id == task_id
            assert result.metadata.status == WorktreeStatus.ACTIVE.value

    @pytest.mark.asyncio
    async def test_create_or_get_worktree_existing(self, worktree_manager, mock_session):
        """Test retrieving an existing worktree metadata."""
        workflow_id = uuid4()
        task_id = uuid4()
        
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Create existing metadata
            existing_metadata = WorktreeMetadata(
                id=uuid4(),
                workflow_id=workflow_id,
                task_id=task_id,
                path="/test/path",
                branch="task/main-test",
                status=WorktreeStatus.ACTIVE.value,
            )
            
            # Mock database query to return existing worktree
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = existing_metadata
            mock_session.query.return_value = mock_query
            
            # Pass None for session to trigger get_db_session
            result = await worktree_manager.create_or_get_worktree(
                workflow_id=workflow_id,
                task_id=task_id,
                base_branch="main",
                session=None,
            )
            
            assert isinstance(result, WorktreeMetadataResult)
            assert result.was_created is False
            assert result.metadata == existing_metadata
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_create_or_get_worktree_max_concurrent(self, worktree_manager, mock_session):
        """Test rejection when max concurrent worktrees reached."""
        workflow_id = uuid4()
        task_id = uuid4()
        
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Mock database query to return no existing worktree but at max capacity
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = None
            mock_query.filter.return_value.count.return_value = worktree_manager.max_concurrent
            mock_session.query.return_value = mock_query
            
            # Pass None for session to trigger get_db_session
            result = await worktree_manager.create_or_get_worktree(
                workflow_id=workflow_id,
                task_id=task_id,
                base_branch="main",
                session=None,
            )
            
            assert isinstance(result, WorktreeMetadataResult)
            assert result.was_created is False
            assert result.metadata is None
            assert "Max concurrent worktrees" in result.error_message

    @pytest.mark.asyncio
    async def test_mark_cleaned_success(self, worktree_manager, mock_session):
        """Test marking worktree as cleaned."""
        task_id = uuid4()
        
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Create existing metadata
            existing_metadata = WorktreeMetadata(
                id=uuid4(),
                workflow_id=uuid4(),
                task_id=task_id,
                path="/test/path",
                branch="task/main-test",
                status=WorktreeStatus.ACTIVE.value,
            )
            
            # Mock database query to return existing worktree
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = existing_metadata
            mock_session.query.return_value = mock_query
            
            # Mock db commit
            mock_session.commit = MagicMock()
            
            # Pass None for session to trigger get_db_session
            success = await worktree_manager.mark_cleaned(task_id=task_id, session=None)
            
            assert success is True
            assert existing_metadata.status == WorktreeStatus.CLEANED.value
            assert existing_metadata.cleaned_at is not None

    @pytest.mark.asyncio
    async def test_mark_cleaned_not_found(self, worktree_manager, mock_session):
        """Test marking worktree as cleaned when not found."""
        task_id = uuid4()
        
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Mock database query to return no existing worktree
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = None
            mock_session.query.return_value = mock_query
            
            # Pass None for session to trigger get_db_session
            success = await worktree_manager.mark_cleaned(task_id=task_id, session=None)
            
            assert success is False

    @pytest.mark.asyncio
    async def test_mark_error_success(self, worktree_manager, mock_session):
        """Test marking worktree as error."""
        task_id = uuid4()
        error_message = "Test error"
        
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Create existing metadata
            existing_metadata = WorktreeMetadata(
                id=uuid4(),
                workflow_id=uuid4(),
                task_id=task_id,
                path="/test/path",
                branch="task/main-test",
                status=WorktreeStatus.ACTIVE.value,
            )
            
            # Mock database query to return existing worktree
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = existing_metadata
            mock_session.query.return_value = mock_query
            
            # Mock db commit
            mock_session.commit = MagicMock()
            
            # Pass None for session to trigger get_db_session
            success = await worktree_manager.mark_error(
                task_id=task_id,
                error_message=error_message,
                session=None,
            )
            
            assert success is True
            assert existing_metadata.status == WorktreeStatus.ERROR.value
            assert existing_metadata.error_message == error_message

    @pytest.mark.asyncio
    async def test_get_active_count(self, worktree_manager, mock_session):
        """Test getting active worktree count."""
        expected_count = 5
        
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Mock database query to return count
            mock_query = MagicMock()
            mock_query.filter.return_value.count.return_value = expected_count
            mock_session.query.return_value = mock_query
            
            # Pass None for session to trigger get_db_session
            count = await worktree_manager.get_active_count(session=None)
            
            assert count == expected_count

    @pytest.mark.asyncio
    async def test_get_worktree_info(self, worktree_manager, mock_session):
        """Test getting worktree info."""
        task_id = uuid4()
        
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Create existing metadata
            existing_metadata = WorktreeMetadata(
                id=uuid4(),
                workflow_id=uuid4(),
                task_id=task_id,
                path="/test/path",
                branch="task/main-test",
                status=WorktreeStatus.ACTIVE.value,
            )
            
            # Mock database query to return existing worktree
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = existing_metadata
            mock_session.query.return_value = mock_query
            
            # Pass None for session to trigger get_db_session
            metadata = await worktree_manager.get_worktree_info(task_id=task_id, session=None)
            
            assert metadata == existing_metadata

    @pytest.mark.asyncio
    async def test_is_worktree_clean_true(self, worktree_manager):
        """Test checking if worktree is clean (returns True)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Mock subprocess to return clean status
            with patch("execqueue.runner.worktree_manager.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = ""
                mock_result.returncode = 0
                mock_run.return_value = mock_result
                
                is_clean = worktree_manager._is_worktree_clean(path)
                
                assert is_clean is True
                mock_run.assert_called_once_with(
                    ["git", "status", "--porcelain"],
                    cwd=str(path),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

    @pytest.mark.asyncio
    async def test_is_worktree_clean_false(self, worktree_manager):
        """Test checking if worktree is clean (returns False)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Mock subprocess to return dirty status
            with patch("execqueue.runner.worktree_manager.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = "M file.txt"
                mock_result.returncode = 0
                mock_run.return_value = mock_result
                
                is_clean = worktree_manager._is_worktree_clean(path)
                
                assert is_clean is False

    @pytest.mark.asyncio
    async def test_remove_worktree_success(self, worktree_manager):
        """Test removing worktree successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "worktree"
            path.mkdir()
            
            # Create a test file
            test_file = path / "test.txt"
            test_file.write_text("test")
            
            # Mock subprocess to return success
            with patch("execqueue.runner.worktree_manager.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_run.return_value = mock_result
                
                worktree_manager._remove_worktree(path)
                
                # Should try git worktree remove first
                mock_run.assert_called_once_with(
                    ["git", "worktree", "remove", "--force"],
                    cwd=str(path),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                
                # Directory should still exist in this mock scenario
                assert path.exists()

    @pytest.mark.asyncio
    async def test_remove_worktree_fallback(self, worktree_manager):
        """Test removing worktree with fallback to shutil."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "worktree"
            path.mkdir()
            
            # Create a test file
            test_file = path / "test.txt"
            test_file.write_text("test")
            
            # Mock subprocess to fail
            with patch("execqueue.runner.worktree_manager.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 1  # Failure
                mock_run.return_value = mock_result
                
                with patch("shutil.rmtree") as mock_rmtree:
                    worktree_manager._remove_worktree(path)
                    
                    # Should try git worktree remove first, then fallback
                    mock_run.assert_called_once_with(
                        ["git", "worktree", "remove", "--force"],
                        cwd=str(path),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    mock_rmtree.assert_called_once_with(path, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_cleanup_orphaned(self, worktree_manager, mock_session):
        """Test cleaning up orphaned worktrees."""
        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Mock get_db_session to return our async context manager
        with patch("execqueue.runner.worktree_manager.get_db_session", return_value=SessionContextManager()):
            # Create old metadata
            old_metadata = WorktreeMetadata(
                id=uuid4(),
                workflow_id=uuid4(),
                task_id=uuid4(),
                path="/nonexistent/path",
                branch="task/main-test",
                status=WorktreeStatus.ACTIVE.value,
                created_at=datetime.now(timezone.utc) - timedelta(hours=25),  # Older than 24h
            )
            
            # Mock database query to return old worktree
            mock_query = MagicMock()
            mock_query.filter.return_value.all.return_value = [old_metadata]
            mock_session.query.return_value = mock_query
            
            # Mock db commit
            mock_session.commit = MagicMock()
            
            with patch.object(worktree_manager, "_is_worktree_clean", return_value=True):
                with patch.object(worktree_manager, "_remove_worktree"):
                    # Pass None for session to trigger get_db_session
                    cleaned_count = await worktree_manager.cleanup_orphaned(
                        ttl_hours=24,
                        session=None,
                    )
                    
                    assert cleaned_count == 1
                    assert old_metadata.status == WorktreeStatus.CLEANED.value
                    assert old_metadata.cleaned_at is not None