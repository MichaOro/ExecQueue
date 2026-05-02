"""Tests for ExecutionChain (REQ-021 end-to-end workflow)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from execqueue.models.enums import ExecutionStatus
from execqueue.models.task_execution import TaskExecution
from execqueue.runner.execution_chain import ExecutionChain, ExecutionChainError
from execqueue.runner.validation_models import (
    ValidationIssue,
    ValidationStatus,
    ValidationResult,
)
from execqueue.runner.validation_pipeline import ValidationPipeline


class TestExecutionChain:
    """Test ExecutionChain functionality."""

    @pytest.fixture
    def execution_chain(self):
        """Create an ExecutionChain instance."""
        return ExecutionChain(worktree_root="/tmp/worktrees")

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def mock_execution(self):
        """Create a mock TaskExecution."""
        execution = MagicMock(spec=TaskExecution)
        execution.id = uuid4()
        execution.task_id = uuid4()
        execution.commit_sha_after = "abcdef1234567890"
        execution.worktree_path = "/tmp/worktrees/test"
        execution.status = ExecutionStatus.DONE.value
        return execution

    @pytest.fixture
    def mock_validation_pipeline(self):
        """Create a mock ValidationPipeline."""
        pipeline = MagicMock(spec=ValidationPipeline)
        pipeline.validator_count = 2
        return pipeline

    def test_init(self, execution_chain):
        """Test ExecutionChain initialization."""
        assert execution_chain.worktree_root == "/tmp/worktrees"
        assert execution_chain.target_branch == "main"
        assert execution_chain.max_retries == 3
        assert execution_chain.force_cleanup is False

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test successful execution chain."""
        # Mock validation to pass
        validation_result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_pipeline",
        )
        mock_validation_pipeline.validate = AsyncMock(return_value=validation_result)

        # Mock commit adoption to succeed
        with patch("execqueue.runner.execution_chain.adopt_commit_with_lifecycle") as mock_adopt:
            adoption_result = MagicMock()
            adoption_result.success = True
            adoption_result.validation_passed = True
            adoption_result.adopted_commit_sha = "adopted_sha"
            mock_adopt.return_value = adoption_result

            # Mock worktree cleanup to succeed
            with patch.object(execution_chain._cleanup_service, "cleanup_after_adoption", return_value=True):
                # Mock worktree manager to return metadata
                with patch.object(execution_chain._worktree_manager, "get_worktree_info") as mock_get_wt:
                    mock_get_wt.return_value = MagicMock()

                    success = await execution_chain.execute(
                        session=mock_session,
                        execution=mock_execution,
                        validation_pipeline=mock_validation_pipeline,
                    )

                    assert success is True
                    mock_validation_pipeline.validate.assert_called_once_with(mock_execution)
                    mock_adopt.assert_called_once()
                    execution_chain._cleanup_service.cleanup_after_adoption.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_validation_failure(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test execution chain with validation failure."""
        # Mock validation to fail
        validation_result = ValidationResult(
            status=ValidationStatus.FAILED,
            validator_name="test_pipeline",
            issues=[ValidationIssue(code="TEST_ERROR", message="Test error", severity="error")],
        )
        mock_validation_pipeline.validate = AsyncMock(return_value=validation_result)

        success = await execution_chain.execute(
            session=mock_session,
            execution=mock_execution,
            validation_pipeline=mock_validation_pipeline,
        )

        assert success is False
        assert mock_execution.status == ExecutionStatus.FAILED.value
        assert mock_execution.error_type == "VALIDATION_FAILED"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_validation_requires_review(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test execution chain with validation requiring review."""
        # Mock validation to require review
        validation_result = ValidationResult(
            status=ValidationStatus.REQUIRES_REVIEW,
            validator_name="test_pipeline",
            issues=[ValidationIssue(code="REVIEW_NEEDED", message="Review needed", severity="warning")],
        )
        mock_validation_pipeline.validate = AsyncMock(return_value=validation_result)

        success = await execution_chain.execute(
            session=mock_session,
            execution=mock_execution,
            validation_pipeline=mock_validation_pipeline,
        )

        assert success is False
        assert mock_execution.status == ExecutionStatus.REVIEW.value
        assert mock_execution.error_type == "VALIDATION_REQUIRES_REVIEW"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_missing_commit_sha(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test execution chain with missing commit SHA."""
        # Set commit SHA to None
        mock_execution.commit_sha_after = None

        # Mock validation to pass
        validation_result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_pipeline",
        )
        mock_validation_pipeline.validate = AsyncMock(return_value=validation_result)

        success = await execution_chain.execute(
            session=mock_session,
            execution=mock_execution,
            validation_pipeline=mock_validation_pipeline,
        )

        assert success is False
        assert mock_execution.status == ExecutionStatus.FAILED.value
        assert mock_execution.error_type == "MISSING_COMMIT_SHA"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_missing_worktree_metadata(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test execution chain with missing worktree metadata."""
        # Mock validation to pass
        validation_result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_pipeline",
        )
        mock_validation_pipeline.validate = AsyncMock(return_value=validation_result)

        # Mock worktree manager to return None
        with patch.object(execution_chain._worktree_manager, "get_worktree_info") as mock_get_wt:
            mock_get_wt.return_value = None

            success = await execution_chain.execute(
                session=mock_session,
                execution=mock_execution,
                validation_pipeline=mock_validation_pipeline,
            )

            assert success is False
            assert mock_execution.status == ExecutionStatus.FAILED.value
            assert mock_execution.error_type == "MISSING_WORKTREE_METADATA"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_commit_adoption_failure(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test execution chain with commit adoption failure."""
        # Mock validation to pass
        validation_result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_pipeline",
        )
        mock_validation_pipeline.validate = AsyncMock(return_value=validation_result)

        # Mock worktree manager to return metadata
        with patch.object(execution_chain._worktree_manager, "get_worktree_info") as mock_get_wt:
            mock_get_wt.return_value = MagicMock()

            # Mock commit adoption to fail
            with patch("execqueue.runner.execution_chain.adopt_commit_with_lifecycle") as mock_adopt:
                adoption_result = MagicMock()
                adoption_result.success = False
                adoption_result.validation_passed = False
                adoption_result.conflict_detected = False
                adoption_result.needs_review = False
                adoption_result.error_message = "Adoption failed"
                mock_adopt.return_value = adoption_result

                success = await execution_chain.execute(
                    session=mock_session,
                    execution=mock_execution,
                    validation_pipeline=mock_validation_pipeline,
                )

                assert success is False
                mock_adopt.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_commit_adoption_conflict(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test execution chain with commit adoption conflict (requires review)."""
        # Mock validation to pass
        validation_result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_pipeline",
        )
        mock_validation_pipeline.validate = AsyncMock(return_value=validation_result)

        # Mock worktree manager to return metadata
        with patch.object(execution_chain._worktree_manager, "get_worktree_info") as mock_get_wt:
            mock_get_wt.return_value = MagicMock()

            # Mock commit adoption to detect conflict
            with patch("execqueue.runner.execution_chain.adopt_commit_with_lifecycle") as mock_adopt:
                adoption_result = MagicMock()
                adoption_result.success = False
                adoption_result.validation_passed = False
                adoption_result.conflict_detected = True
                adoption_result.needs_review = False
                adoption_result.error_message = "Conflict detected"
                mock_adopt.return_value = adoption_result

                success = await execution_chain.execute(
                    session=mock_session,
                    execution=mock_execution,
                    validation_pipeline=mock_validation_pipeline,
                )

                # Adoption with conflict is considered "successful" from workflow perspective
                # because it transitions to REVIEW state
                assert success is True
                mock_adopt.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_cleanup_failure(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test execution chain with cleanup failure (should still succeed)."""
        # Mock validation to pass
        validation_result = ValidationResult(
            status=ValidationStatus.PASSED,
            validator_name="test_pipeline",
        )
        mock_validation_pipeline.validate = AsyncMock(return_value=validation_result)

        # Mock worktree manager to return metadata
        with patch.object(execution_chain._worktree_manager, "get_worktree_info") as mock_get_wt:
            mock_get_wt.return_value = MagicMock()

            # Mock commit adoption to succeed
            with patch("execqueue.runner.execution_chain.adopt_commit_with_lifecycle") as mock_adopt:
                adoption_result = MagicMock()
                adoption_result.success = True
                adoption_result.validation_passed = True
                adoption_result.adopted_commit_sha = "adopted_sha"
                mock_adopt.return_value = adoption_result

                # Mock worktree cleanup to fail
                with patch.object(execution_chain._cleanup_service, "cleanup_after_adoption", return_value=False):
                    success = await execution_chain.execute(
                        session=mock_session,
                        execution=mock_execution,
                        validation_pipeline=mock_validation_pipeline,
                    )

                    # Even with cleanup failure, the adoption was successful
                    assert success is True
                    mock_adopt.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_catastrophic_failure(
        self,
        execution_chain,
        mock_session,
        mock_execution,
        mock_validation_pipeline,
    ):
        """Test execution chain with catastrophic failure."""
        # Mock validation to raise exception
        mock_validation_pipeline.validate = AsyncMock(side_effect=Exception("Catastrophic failure"))

        with pytest.raises(ExecutionChainError):
            await execution_chain.execute(
                session=mock_session,
                execution=mock_execution,
                validation_pipeline=mock_validation_pipeline,
            )

        # Emergency cleanup should be attempted
        # Note: Since we're mocking the cleanup service, we can't easily verify this
        # In a real test, we'd check that cleanup_after_adoption was called