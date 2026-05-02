"""Additional unit tests for ExecutionChain functionality."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from execqueue.models.task_execution import TaskExecution
from execqueue.models.enums import ExecutionStatus
from execqueue.runner.execution_chain import ExecutionChain
from execqueue.runner.validation_pipeline import ValidationPipeline
from execqueue.runner.validator import MockValidator


class TestExecutionChainBasicFunctionality:
    """Basic tests for ExecutionChain functionality."""

    @pytest.mark.asyncio
    async def test_execution_chain_initialization(self):
        """Test that ExecutionChain initializes correctly."""
        chain = ExecutionChain(
            worktree_root="/tmp/worktrees",
            target_branch="main",
            max_retries=3,
            force_cleanup=False,
        )
        
        assert chain.worktree_root == "/tmp/worktrees"
        assert chain.target_branch == "main"
        assert chain.max_retries == 3
        assert chain.force_cleanup is False

    @pytest.mark.asyncio
    async def test_execution_chain_execute_method_exists(self):
        """Test that ExecutionChain has an execute method."""
        chain = ExecutionChain(
            worktree_root="/tmp/worktrees",
            target_branch="main",
        )
        
        # Just check that the method exists and is callable
        assert hasattr(chain, 'execute')
        assert callable(getattr(chain, 'execute'))

    @pytest.mark.asyncio
    async def test_validation_pipeline_can_be_created(self):
        """Test that we can create a ValidationPipeline with validators."""
        # Create a simple mock validator
        validator = MockValidator(always_pass=True)
        
        # Create validation pipeline
        pipeline = ValidationPipeline(validators=[validator])
        
        assert pipeline.validator_count == 1