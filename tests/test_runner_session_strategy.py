"""Tests for HybridSessionStrategy (REQ-016 WP02)."""

from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from execqueue.runner.session_strategy import (
    HybridSessionStrategy,
    SessionAssignment,
    SessionPlan,
)


@pytest.fixture
def mock_opencode_client():
    """Create a mock OpenCode client."""
    client = MagicMock()
    
    # Mock create_session to return a coroutine that returns a session object with an ID
    async def mock_create_session(name: str):
        session = MagicMock()
        session.id = f"session-{name}-xyz"
        return session
    
    client.create_session = AsyncMock(side_effect=mock_create_session)
    
    # Mock close_session
    client.close_session = AsyncMock()
    
    return client


class TestSessionAssignment:
    """Test SessionAssignment dataclass."""

    def test_assignment_creation(self):
        """Test creating a session assignment."""
        task_ids = [uuid4(), uuid4()]
        assignment = SessionAssignment(
            session_id="test-session",
            task_ids=task_ids,
            is_sequential=True,
        )
        
        assert assignment.session_id == "test-session"
        assert assignment.task_ids == task_ids
        assert assignment.is_sequential is True

    def test_assignment_parallel(self):
        """Test parallel assignment."""
        task_id = uuid4()
        assignment = SessionAssignment(
            session_id="parallel-session",
            task_ids=[task_id],
            is_sequential=False,
        )
        
        assert assignment.is_sequential is False
        assert len(assignment.task_ids) == 1


class TestSessionPlan:
    """Test SessionPlan dataclass."""

    def test_empty_plan(self):
        """Test empty session plan."""
        plan = SessionPlan()
        
        assert len(plan.assignments) == 0
        assert plan.sequential_count == 0
        assert plan.parallel_count == 0

    def test_plan_with_assignments(self):
        """Test plan with mixed assignments."""
        task_ids = [uuid4(), uuid4(), uuid4()]
        assignments = [
            SessionAssignment(session_id="seq-1", task_ids=task_ids[:2], is_sequential=True),
            SessionAssignment(session_id="parallel-1", task_ids=[task_ids[2]], is_sequential=False),
        ]
        plan = SessionPlan(assignments=assignments)
        
        assert len(plan.assignments) == 2
        assert plan.sequential_count == 1
        assert plan.parallel_count == 1

    def test_get_session_for_task(self):
        """Test getting session for a specific task."""
        task1, task2, task3 = uuid4(), uuid4(), uuid4()
        assignments = [
            SessionAssignment(session_id="seq-1", task_ids=[task1, task2], is_sequential=True),
            SessionAssignment(session_id="parallel-1", task_ids=[task3], is_sequential=False),
        ]
        plan = SessionPlan(assignments=assignments)
        
        assert plan.get_session_for_task(task1) == "seq-1"
        assert plan.get_session_for_task(task2) == "seq-1"
        assert plan.get_session_for_task(task3) == "parallel-1"
        assert plan.get_session_for_task(uuid4()) is None  # Unknown task

    def test_get_tasks_for_session(self):
        """Test getting tasks for a specific session."""
        task1, task2, task3 = uuid4(), uuid4(), uuid4()
        assignments = [
            SessionAssignment(session_id="seq-1", task_ids=[task1, task2], is_sequential=True),
            SessionAssignment(session_id="parallel-1", task_ids=[task3], is_sequential=False),
        ]
        plan = SessionPlan(assignments=assignments)
        
        assert set(plan.get_tasks_for_session("seq-1")) == {task1, task2}
        assert plan.get_tasks_for_session("parallel-1") == [task3]
        assert plan.get_tasks_for_session("unknown") == []


class TestHybridSessionStrategyCreatePlan:
    """Test HybridSessionStrategy.create_plan()."""

    def test_empty_inputs(self):
        """Test with empty sequential paths and no tasks."""
        client = AsyncMock()
        strategy = HybridSessionStrategy(client)
        
        plan = strategy.create_plan([], [])
        
        assert len(plan.assignments) == 0
        assert plan.sequential_count == 0
        assert plan.parallel_count == 0

    def test_single_sequential_path(self):
        """Test single sequential path with 3 tasks."""
        client = AsyncMock()
        strategy = HybridSessionStrategy(client)
        
        task1, task2, task3 = uuid4(), uuid4(), uuid4()
        sequential_paths = [[task1, task2, task3]]
        
        plan = strategy.create_plan(sequential_paths, [task1, task2, task3])
        
        assert len(plan.assignments) == 1
        assert plan.sequential_count == 1
        assert plan.parallel_count == 0
        
        assignment = plan.assignments[0]
        assert assignment.is_sequential is True
        assert set(assignment.task_ids) == {task1, task2, task3}

    def test_multiple_sequential_paths(self):
        """Test multiple independent sequential paths."""
        client = AsyncMock()
        strategy = HybridSessionStrategy(client)
        
        path1 = [uuid4(), uuid4()]
        path2 = [uuid4(), uuid4(), uuid4()]
        all_tasks = path1 + path2
        
        plan = strategy.create_plan([path1, path2], all_tasks)
        
        assert len(plan.assignments) == 2
        assert plan.sequential_count == 2
        assert plan.parallel_count == 0

    def test_parallel_tasks_from_sequential_paths(self):
        """Test that tasks not in paths become parallel tasks."""
        client = AsyncMock()
        strategy = HybridSessionStrategy(client)
        
        task1, task2 = uuid4(), uuid4()
        task3 = uuid4()  # Not in any path
        
        sequential_paths = [[task1, task2]]
        all_tasks = [task1, task2, task3]
        
        plan = strategy.create_plan(sequential_paths, all_tasks)
        
        assert len(plan.assignments) == 2  # 1 sequential + 1 parallel
        assert plan.sequential_count == 1
        assert plan.parallel_count == 1
        
        # Find parallel assignment
        parallel_assignments = [a for a in plan.assignments if not a.is_sequential]
        assert len(parallel_assignments) == 1
        assert parallel_assignments[0].task_ids == [task3]

    def test_session_naming(self):
        """Test that session names are descriptive."""
        client = AsyncMock()
        strategy = HybridSessionStrategy(client)
        
        task_ids = [uuid4(), uuid4(), uuid4()]
        plan = strategy.create_plan([task_ids], task_ids)
        
        assignment = plan.assignments[0]
        assert assignment.session_id.startswith("seq-")
        assert "3tasks" in assignment.session_id


class TestHybridSessionStrategyCreateSessions:
    """Test HybridSessionStrategy.create_sessions()."""

    @pytest.mark.asyncio
    async def test_creates_sessions_for_all_assignments(self, mock_opencode_client):
        """Test that sessions are created for all assignments."""
        strategy = HybridSessionStrategy(mock_opencode_client)
        
        task_ids = [uuid4(), uuid4()]
        plan = SessionPlan([
            SessionAssignment(session_id="placeholder-1", task_ids=task_ids, is_sequential=True),
        ])
        
        result_plan = await strategy.create_sessions(plan)
        
        # Verify client.create_session was called
        assert mock_opencode_client.create_session.call_count == 1
        
        # Verify session_id was updated
        assert result_plan.assignments[0].session_id != "placeholder-1"
        assert result_plan.assignments[0].session_id.startswith("session-")

    @pytest.mark.asyncio
    async def test_creates_multiple_sessions(self, mock_opencode_client):
        """Test creating multiple sessions."""
        strategy = HybridSessionStrategy(mock_opencode_client)
        
        task1, task2 = uuid4(), uuid4()
        plan = SessionPlan([
            SessionAssignment(session_id="seq-1", task_ids=[task1], is_sequential=True),
            SessionAssignment(session_id="parallel-1", task_ids=[task2], is_sequential=False),
        ])
        
        await strategy.create_sessions(plan)
        
        # Should create 2 sessions
        assert mock_opencode_client.create_session.call_count == 2


class TestHybridSessionStrategyCleanupSessions:
    """Test HybridSessionStrategy.cleanup_sessions()."""

    @pytest.mark.asyncio
    async def test_cleans_up_all_sessions(self, mock_opencode_client):
        """Test that all sessions are cleaned up."""
        strategy = HybridSessionStrategy(mock_opencode_client)
        
        task1, task2 = uuid4(), uuid4()
        plan = SessionPlan([
            SessionAssignment(session_id="session-1", task_ids=[task1], is_sequential=True),
            SessionAssignment(session_id="session-2", task_ids=[task2], is_sequential=False),
        ])
        
        await strategy.cleanup_sessions(plan)
        
        # Verify close_session was called for each unique session
        assert mock_opencode_client.close_session.call_count == 2

    @pytest.mark.asyncio
    async def test_cleans_up_shared_sessions_once(self, mock_opencode_client):
        """Test that shared sessions (sequential paths) are cleaned up once."""
        strategy = HybridSessionStrategy(mock_opencode_client)
        
        task1, task2, task3 = uuid4(), uuid4(), uuid4()
        # Two assignments sharing the same session_id
        plan = SessionPlan([
            SessionAssignment(session_id="shared-session", task_ids=[task1], is_sequential=True),
            SessionAssignment(session_id="shared-session", task_ids=[task2, task3], is_sequential=True),
        ])
        
        await strategy.cleanup_sessions(plan)
        
        # Should only close once even though session appears twice
        mock_opencode_client.close_session.assert_called_once_with("shared-session")

    @pytest.mark.asyncio
    async def test_continues_on_close_error(self, mock_opencode_client):
        """Test that cleanup continues even if some sessions fail to close."""
        strategy = HybridSessionStrategy(mock_opencode_client)
        
        # Track call count manually
        call_count = 0
        
        # First close fails, second succeeds
        async def mock_close_with_error(session_id):
            nonlocal call_count
            call_count += 1
            if session_id == "session-1":
                raise Exception("Close failed")
        
        mock_opencode_client.close_session = AsyncMock(side_effect=mock_close_with_error)
        
        task1, task2 = uuid4(), uuid4()
        plan = SessionPlan([
            SessionAssignment(session_id="session-1", task_ids=[task1], is_sequential=True),
            SessionAssignment(session_id="session-2", task_ids=[task2], is_sequential=False),
        ])
        
        # Should not raise even though session-1 fails
        await strategy.cleanup_sessions(plan)
        
        # Both sessions should have been attempted
        assert call_count == 2


class TestHybridSessionStrategyIntegration:
    """Integration tests for HybridSessionStrategy."""

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self, mock_opencode_client):
        """Test complete session lifecycle: plan → create → cleanup."""
        strategy = HybridSessionStrategy(mock_opencode_client)
        
        # Create a realistic workflow scenario
        task1, task2, task3, task4 = uuid4(), uuid4(), uuid4(), uuid4()
        sequential_paths = [[task1, task2]]  # task1 → task2 sequential
        all_tasks = [task1, task2, task3, task4]  # task3, task4 are parallel
        
        # Step 1: Create plan
        plan = strategy.create_plan(sequential_paths, all_tasks)
        assert plan.sequential_count == 1
        assert plan.parallel_count == 2
        
        # Step 2: Create actual sessions
        plan = await strategy.create_sessions(plan)
        assert mock_opencode_client.create_session.call_count == 3
        
        # Step 3: Verify sessions can be looked up
        for task_id in all_tasks:
            session_id = plan.get_session_for_task(task_id)
            assert session_id is not None
            assert session_id.startswith("session-")
        
        # Step 4: Cleanup
        await strategy.cleanup_sessions(plan)
        assert mock_opencode_client.close_session.call_count == 3
