"""Tests for WorktreeCleanupService (REQ-021 Section 6)."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from execqueue.db.models import WorktreeMetadata, WorktreeStatus
from execqueue.runner.worktree_cleanup import WorktreeCleanupService


class TestWorktreeCleanupService:
    """Test WorktreeCleanupService functionality."""

    @pytest.fixture
    def cleanup_service(self):
        """Create a WorktreeCleanupService instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield WorktreeCleanupService(worktree_root=tmpdir)

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock(spec=Session)

    def test_init(self, cleanup_service):
        """Test WorktreeCleanupService initialization."""
        assert cleanup_service.worktree_root.exists()
        assert cleanup_service.max_retries == 3
        assert cleanup_service.force_cleanup is False

    @pytest.mark.asyncio
    async def test_cleanup_after_adoption_success(self, cleanup_service, mock_session):
        """Test successful cleanup after adoption."""
        task_id = uuid4()
        
        # Create metadata
        metadata = WorktreeMetadata(
            id=uuid4(),
            workflow_id=uuid4(),
            task_id=task_id,
            path="/test/path",
            branch="task/main-test",
            status=WorktreeStatus.ACTIVE.value,
        )
        
        # Mock database query to return metadata
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = metadata
        mock_session.query.return_value = mock_query
        
        # Mock db commit
        mock_session.commit = MagicMock()
        
        # Mock cleanup worktree to return success
        with patch.object(cleanup_service, "_cleanup_worktree", return_value=True):
            success = await cleanup_service.cleanup_after_adoption(
                task_id=task_id,
                session=mock_session,
            )
            
            assert success is True
            assert metadata.status == WorktreeStatus.CLEANED.value
            assert metadata.cleaned_at is not None

    @pytest.mark.asyncio
    async def test_cleanup_after_adoption_no_metadata(self, cleanup_service, mock_session):
        """Test cleanup when no metadata found."""
        task_id = uuid4()
        
        # Mock database query to return no metadata
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_session.query.return_value = mock_query
        
        success = await cleanup_service.cleanup_after_adoption(
            task_id=task_id,
            session=mock_session,
        )
        
        assert success is False

    @pytest.mark.asyncio
    async def test_cleanup_after_adoption_failure_with_retry(self, cleanup_service, mock_session):
        """Test cleanup failure with retry attempts."""
        task_id = uuid4()
        
        # Create metadata
        metadata = WorktreeMetadata(
            id=uuid4(),
            workflow_id=uuid4(),
            task_id=task_id,
            path="/test/path",
            branch="task/main-test",
            status=WorktreeStatus.ACTIVE.value,
        )
        
        # Mock database query to return metadata
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = metadata
        mock_session.query.return_value = mock_query
        
        # Mock db commit
        mock_session.commit = MagicMock()
        
        # Mock cleanup worktree to return failure
        with patch.object(cleanup_service, "_cleanup_worktree", return_value=False):
            success = await cleanup_service.cleanup_after_adoption(
                task_id=task_id,
                session=mock_session,
            )
            
            assert success is False
            assert metadata.status == WorktreeStatus.ERROR.value
            assert "failed after 3 attempts" in metadata.error_message

    @pytest.mark.asyncio
    async def test_cleanup_worktree_path_does_not_exist(self, cleanup_service):
        """Test cleanup when worktree path does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent"
            
            success = await cleanup_service._cleanup_worktree(path)
            
            assert success is True

    @pytest.mark.asyncio
    async def test_cleanup_worktree_success(self, cleanup_service):
        """Test successful worktree cleanup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Mock subprocess to return success
            with patch("execqueue.runner.worktree_cleanup.subprocess.run") as mock_run:
                # First call (is_worktree_clean) returns clean
                mock_result1 = MagicMock()
                mock_result1.stdout = ""
                mock_result1.returncode = 0
                
                # Second call (git worktree remove) returns success
                mock_result2 = MagicMock()
                mock_result2.returncode = 0
                
                mock_run.side_effect = [mock_result1, mock_result2]
                
                with patch.object(cleanup_service, "_is_worktree_clean", return_value=True):
                    success = await cleanup_service._cleanup_worktree(path)
                    
                    assert success is True

    @pytest.mark.asyncio
    async def test_cleanup_worktree_dirty_without_force(self, cleanup_service):
        """Test cleanup of dirty worktree without force flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            with patch.object(cleanup_service, "_is_worktree_clean", return_value=False):
                success = await cleanup_service._cleanup_worktree(path, force=False)
                
                assert success is False

    @pytest.mark.asyncio
    async def test_is_worktree_clean_true(self, cleanup_service):
        """Test checking if worktree is clean (returns True)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Mock subprocess to return clean status
            with patch("execqueue.runner.worktree_cleanup.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = ""
                mock_result.returncode = 0
                mock_run.return_value = mock_result
                
                is_clean = cleanup_service._is_worktree_clean(path)
                
                assert is_clean is True

    @pytest.mark.asyncio
    async def test_is_worktree_clean_false(self, cleanup_service):
        """Test checking if worktree is clean (returns False)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Mock subprocess to return dirty status
            with patch("execqueue.runner.worktree_cleanup.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.stdout = "M file.txt"
                mock_result.returncode = 0
                mock_run.return_value = mock_result
                
                is_clean = cleanup_service._is_worktree_clean(path)
                
                assert is_clean is False

    @pytest.mark.asyncio
    async def test_orphaned_cleanup_job_success(self, cleanup_service, mock_session):
        """Test successful orphaned cleanup job."""
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
        
        with patch.object(cleanup_service, "_is_worktree_clean", return_value=True):
            with patch.object(cleanup_service, "_cleanup_worktree", return_value=True):
                cleaned_count = await cleanup_service.orphaned_cleanup_job(
                    ttl_hours=24,
                    session=mock_session,
                )
                
                assert cleaned_count == 1
                assert old_metadata.status == WorktreeStatus.CLEANED.value
                assert old_metadata.cleaned_at is not None

    @pytest.mark.asyncio
    async def test_orphaned_cleanup_job_dirty_without_force(self, cleanup_service, mock_session):
        """Test orphaned cleanup job skips dirty worktree without force."""
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
        
        with patch.object(cleanup_service, "_is_worktree_clean", return_value=False):
            cleaned_count = await cleanup_service.orphaned_cleanup_job(
                ttl_hours=24,
                force=False,
                session=mock_session,
            )
            
            assert cleaned_count == 0
            assert old_metadata.status == WorktreeStatus.ERROR.value
            assert "dirty worktree" in old_metadata.error_message

    @pytest.mark.asyncio
    async def test_get_orphaned_count(self, cleanup_service, mock_session):
        """Test getting orphaned worktree count."""
        expected_count = 3
        
        # Mock database query to return count
        mock_query = MagicMock()
        mock_query.filter.return_value.count.return_value = expected_count
        mock_session.query.return_value = mock_query
        
        count = await cleanup_service.get_orphaned_count(
            ttl_hours=24,
            session=mock_session,
        )
        
        assert count == expected_count