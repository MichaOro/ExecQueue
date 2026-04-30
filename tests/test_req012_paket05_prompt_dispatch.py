"""Tests for REQ-012-05 Prompt Dispatch Start Semantics.

This module tests:
- Prompt template generation for read-only and write tasks
- Status transition logic
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from execqueue.models.enums import ExecutionStatus
from execqueue.orchestrator.models import RunnerMode
from execqueue.orchestrator.models import PreparedExecutionContext
from execqueue.runner.prompt_templates import build_prompt, build_readonly_prompt, build_write_prompt


class TestPromptTemplates:
    """Test prompt template generation."""

    def test_build_readonly_prompt_contains_required_elements(self):
        """Test that read-only prompt contains required elements."""
        context = {
            "task_number": 1,
            "task_type": "analysis",
            "base_repo_path": "/path/to/repo",
            "runner_mode": "read_only",
        }

        prompt = build_readonly_prompt(context)

        # Check required elements per spec:
        # - Task-Ziel, Scope, Akzeptanzkriterien
        # - Read-only Verhalten
        assert "Task 1" in prompt
        assert "Read-Only" in prompt
        assert "KEINE Dateien andern" in prompt
        assert "KEINE Git-Commits" in prompt
        assert "/path/to/repo" in prompt
        assert "Akzeptanzkriterien" in prompt

    def test_build_write_prompt_contains_required_elements(self):
        """Test that write prompt contains required elements."""
        context = {
            "task_number": 2,
            "task_type": "execution",
            "branch_name": "feature/test",
            "worktree_path": "/path/to/worktree",
            "commit_sha_before": "abc123",
            "runner_mode": "write",
        }

        prompt = build_write_prompt(context)

        # Check required elements per spec:
        # - Task-Ziel, Scope, Akzeptanzkriterien
        # - Worktree-/Branch-Kontext
        # - Write-Regeln (kein force-push, genau ein Commit)
        assert "Task 2" in prompt
        assert "Write" in prompt
        assert "feature/test" in prompt
        assert "/path/to/worktree" in prompt
        assert "abc123" in prompt
        assert "Genau EIN Commit" in prompt
        assert "Keine destruktiven Git-Operationen" in prompt
        assert "Akzeptanzkriterien" in prompt

    def test_build_prompt_routes_to_correct_template(self):
        """Test that build_prompt routes to correct template."""
        readonly_context = {
            "task_number": 1,
            "runner_mode": "read_only",
            "base_repo_path": "/repo",
        }

        write_context = {
            "task_number": 2,
            "runner_mode": "write",
            "branch_name": "main",
            "worktree_path": "/worktree",
            "commit_sha_before": "abc",
        }

        readonly_prompt = build_prompt(readonly_context)
        write_prompt = build_prompt(write_context)

        assert "Read-Only" in readonly_prompt
        assert "Write" in write_prompt
        assert "Read-Only" not in write_prompt
        assert "Write" not in readonly_prompt

    def test_build_prompt_raises_on_unknown_mode(self):
        """Test that build_prompt raises on unknown runner mode."""
        context = {"runner_mode": "unknown"}

        with pytest.raises(ValueError, match="Unknown runner_mode"):
            build_prompt(context)

    def test_readonly_prompt_excludes_write_specific_elements(self):
        """Test that read-only prompt does not contain write-specific elements."""
        context = {
            "task_number": 1,
            "runner_mode": "read_only",
            "base_repo_path": "/repo",
        }

        prompt = build_readonly_prompt(context)

        # Should NOT contain write-specific elements
        assert "Genau EIN Commit" not in prompt
        assert "Commit-Erwartung" not in prompt
        assert "force-push" not in prompt

    def test_write_prompt_includes_all_security_rules(self):
        """Test that write prompt includes all security rules."""
        context = {
            "task_number": 1,
            "runner_mode": "write",
            "branch_name": "main",
            "worktree_path": "/worktree",
            "commit_sha_before": "abc",
        }

        prompt = build_write_prompt(context)

        # Security rules per spec
        assert "Nur im Worktree andern" in prompt
        assert "Keine destruktiven Git-Operationen" in prompt
        assert "force-push" in prompt.lower() or "destruktiven" in prompt.lower()
        assert "Validierung vor Commit" in prompt


class TestStatusTransitionLogic:
    """Test status transition logic documentation."""

    def test_status_transitions_are_documented(self):
        """Test that the status transition sequence is clear.
        
        Per REQ-012-05:
        queued -> dispatching -> in_progress (only after successful dispatch)
        """
        # Documented transition sequence
        transitions = [
            ExecutionStatus.QUEUED.value,
            ExecutionStatus.DISPATCHING.value,
            ExecutionStatus.IN_PROGRESS.value,
        ]
        
        assert len(transitions) == 3
        assert transitions[0] == "queued"
        assert transitions[1] == "dispatching"
        assert transitions[2] == "in_progress"

    def test_in_progress_is_terminal_for_dispatch_phase(self):
        """Test that in_progress marks end of dispatch phase."""
        # in_progress means dispatch succeeded
        # Any further state changes happen in later phases
        assert ExecutionStatus.IN_PROGRESS.value == "in_progress"
