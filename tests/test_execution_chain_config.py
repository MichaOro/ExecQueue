"""Tests for ExecutionChain configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from execqueue.runner.config import RunnerConfig
from execqueue.runner.execution_chain import ExecutionChain


def test_execution_chain_from_config() -> None:
    """Test creating ExecutionChain from RunnerConfig."""
    config = RunnerConfig(
        runner_id="test-runner",
        worktree_root="/tmp/test-worktrees",
        worktree_max_concurrent=5,
        worktree_cleanup_max_retries=2,
        worktree_cleanup_force=True,
        adoption_target_branch="develop",
    )
    
    chain = ExecutionChain(config=config)
    
    assert chain.config == config
    assert chain.worktree_root == config.worktree_root
    assert chain.target_branch == config.adoption_target_branch
    assert chain.max_retries == config.worktree_cleanup_max_retries
    assert chain.force_cleanup == config.worktree_cleanup_force


def test_execution_chain_default_config() -> None:
    """Test creating ExecutionChain with default config."""
    config = RunnerConfig.create_default()
    
    chain = ExecutionChain(config=config)
    
    assert chain.config == config
    assert chain.worktree_root == config.worktree_root
    assert chain.target_branch == config.adoption_target_branch
    assert chain.max_retries == config.worktree_cleanup_max_retries
    assert chain.force_cleanup == config.worktree_cleanup_force


def test_execution_chain_components_initialized() -> None:
    """Test that ExecutionChain components are properly initialized."""
    config = RunnerConfig.create_default()
    chain = ExecutionChain(config=config)
    
    # Check that components are initialized
    assert chain._worktree_manager is not None
    assert chain._cleanup_service is not None
    
    # Check that worktree manager has correct settings
    assert chain._worktree_manager.worktree_root == Path(config.worktree_root)
    assert chain._worktree_manager.max_concurrent == config.worktree_max_concurrent
    
    # Check that cleanup service has correct settings
    assert chain._cleanup_service.worktree_root == Path(config.worktree_root)
    assert chain._cleanup_service.max_retries == config.worktree_cleanup_max_retries
    assert chain._cleanup_service.force_cleanup == config.worktree_cleanup_force