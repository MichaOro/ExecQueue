"""Tests for task grouping engine."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from uuid import uuid4, UUID

from execqueue.db.models import Task
from execqueue.orchestrator.grouping import TaskGroup, TaskGroupingEngine


def create_mock_task(
    task_id: str | None = None,
    task_number: int = 1,
    requirement_id: str | None = None,
    details: dict | None = None,
    status: str = "backlog",
) -> Task:
    """Helper to create mock Task instances."""
    task = MagicMock(spec=Task)
    task.id = uuid4() if task_id is None else UUID(task_id)
    task.task_number = task_number
    task.requirement_id = UUID(requirement_id) if requirement_id else None
    task.details = details or {}
    task.status = status
    return task


class TestTaskGroup:
    """Tests for TaskGroup dataclass."""

    def test_task_group_creation_requirement(self):
        """Test TaskGroup creation for requirement type."""
        req_id = uuid4()
        task = create_mock_task(requirement_id=str(req_id))
        
        group = TaskGroup(
            group_id=req_id,
            tasks=[task],
            group_type="requirement",
            requirement_id=req_id,
        )
        
        assert group.group_id == req_id
        assert len(group.tasks) == 1
        assert group.group_type == "requirement"
        assert group.requirement_id == req_id
        assert group.epic_id is None

    def test_task_group_creation_epic(self):
        """Test TaskGroup creation for epic type."""
        epic_id = uuid4()
        
        group = TaskGroup(
            group_id=epic_id,
            tasks=[],
            group_type="epic",
            epic_id=epic_id,
        )
        
        assert group.group_id == epic_id
        assert group.group_type == "epic"
        assert group.epic_id == epic_id

    def test_task_group_creation_standalone(self):
        """Test TaskGroup creation for standalone type."""
        group_id = uuid4()
        
        group = TaskGroup(
            group_id=group_id,
            tasks=[],
            group_type="standalone",
        )
        
        assert group.group_id == group_id
        assert group.group_type == "standalone"


class TestTaskGroupingEngine:
    """Tests for TaskGroupingEngine."""

    def test_group_by_requirement_single(self):
        """Test grouping by requirement_id with single task."""
        engine = TaskGroupingEngine()
        req_id = uuid4()
        task = create_mock_task(requirement_id=str(req_id))
        
        groups = engine.group_by_requirement([task])
        
        assert len(groups) == 1
        assert req_id in groups
        assert groups[req_id].group_type == "requirement"
        assert len(groups[req_id].tasks) == 1

    def test_group_by_requirement_multiple(self):
        """Test grouping by requirement_id with multiple tasks."""
        engine = TaskGroupingEngine()
        req_id = uuid4()
        task1 = create_mock_task(task_number=1, requirement_id=str(req_id))
        task2 = create_mock_task(task_number=2, requirement_id=str(req_id))
        task3 = create_mock_task(task_number=3, requirement_id=str(req_id))
        
        groups = engine.group_by_requirement([task1, task2, task3])
        
        assert len(groups) == 1
        assert len(groups[req_id].tasks) == 3

    def test_group_by_requirement_multiple_requirements(self):
        """Test grouping by requirement_id with multiple requirements."""
        engine = TaskGroupingEngine()
        req1 = uuid4()
        req2 = uuid4()
        task1 = create_mock_task(task_number=1, requirement_id=str(req1))
        task2 = create_mock_task(task_number=2, requirement_id=str(req1))
        task3 = create_mock_task(task_number=3, requirement_id=str(req2))
        
        groups = engine.group_by_requirement([task1, task2, task3])
        
        assert len(groups) == 2
        assert len(groups[req1].tasks) == 2
        assert len(groups[req2].tasks) == 1

    def test_group_by_requirement_no_requirement_id(self):
        """Test grouping ignores tasks without requirement_id."""
        engine = TaskGroupingEngine()
        task = create_mock_task(requirement_id=None)
        
        groups = engine.group_by_requirement([task])
        
        assert len(groups) == 0

    def test_group_by_epic(self):
        """Test grouping by epic_id from details."""
        engine = TaskGroupingEngine()
        epic_id = uuid4()
        task1 = create_mock_task(task_number=1, details={"epic_id": str(epic_id)})
        task2 = create_mock_task(task_number=2, details={"epic_id": str(epic_id)})
        task3 = create_mock_task(task_number=3, details={"epic_id": str(uuid4())})
        
        groups = engine.group_by_epic([task1, task2, task3])
        
        assert len(groups) == 2
        assert epic_id in groups
        assert len(groups[epic_id].tasks) == 2

    def test_group_by_epic_invalid_epic_id(self):
        """Test grouping ignores invalid epic_id."""
        engine = TaskGroupingEngine()
        task = create_mock_task(details={"epic_id": "invalid-uuid"})
        
        groups = engine.group_by_epic([task])
        
        assert len(groups) == 0

    def test_group_by_epic_no_epic_id(self):
        """Test grouping ignores tasks without epic_id."""
        engine = TaskGroupingEngine()
        task = create_mock_task(details={})
        
        groups = engine.group_by_epic([task])
        
        assert len(groups) == 0

    def test_group_standalone(self):
        """Test standalone grouping creates one group per task."""
        engine = TaskGroupingEngine()
        task1 = create_mock_task(task_number=1)
        task2 = create_mock_task(task_number=2)
        
        groups = engine.group_standalone([task1, task2])
        
        assert len(groups) == 2
        for group in groups:
            assert group.group_type == "standalone"
            assert len(group.tasks) == 1

    def test_group_standalone_excludes_requirement_id(self):
        """Test standalone excludes tasks with requirement_id."""
        engine = TaskGroupingEngine()
        req_id = uuid4()
        task1 = create_mock_task(task_number=1, requirement_id=str(req_id))
        task2 = create_mock_task(task_number=2)
        
        groups = engine.group_standalone([task1, task2])
        
        assert len(groups) == 1
        assert groups[0].tasks[0].task_number == 2

    def test_group_standalone_excludes_epic_id(self):
        """Test standalone excludes tasks with epic_id."""
        engine = TaskGroupingEngine()
        task1 = create_mock_task(task_number=1, details={"epic_id": str(uuid4())})
        task2 = create_mock_task(task_number=2)
        
        groups = engine.group_standalone([task1, task2])
        
        assert len(groups) == 1
        assert groups[0].tasks[0].task_number == 2

    def test_create_groups_priority_requirement(self):
        """Test create_groups prioritizes requirement_id over epic_id."""
        engine = TaskGroupingEngine()
        req_id = uuid4()
        epic_id = uuid4()
        # Task has both requirement_id and epic_id - should use requirement
        task = create_mock_task(
            task_number=1,
            requirement_id=str(req_id),
            details={"epic_id": str(epic_id)},
        )
        
        groups = engine.create_groups(MagicMock(), [task])
        
        assert len(groups) == 1
        assert groups[0].group_type == "requirement"
        assert groups[0].group_id == req_id

    def test_create_groups_priority_epic_over_standalone(self):
        """Test create_groups prioritizes epic_id over standalone."""
        engine = TaskGroupingEngine()
        epic_id = uuid4()
        task = create_mock_task(
            task_number=1,
            details={"epic_id": str(epic_id)},
        )
        
        groups = engine.create_groups(MagicMock(), [task])
        
        assert len(groups) == 1
        assert groups[0].group_type == "epic"

    def test_create_groups_mixed(self):
        """Test create_groups with mixed task types."""
        engine = TaskGroupingEngine()
        req_id = uuid4()
        epic_id = uuid4()
        
        task1 = create_mock_task(task_number=1, requirement_id=str(req_id))
        task2 = create_mock_task(task_number=2, requirement_id=str(req_id))
        task3 = create_mock_task(task_number=3, details={"epic_id": str(epic_id)})
        task4 = create_mock_task(task_number=4)
        
        groups = engine.create_groups(MagicMock(), [task1, task2, task3, task4])
        
        assert len(groups) == 3
        
        # Find each group type
        req_groups = [g for g in groups if g.group_type == "requirement"]
        epic_groups = [g for g in groups if g.group_type == "epic"]
        standalone_groups = [g for g in groups if g.group_type == "standalone"]
        
        assert len(req_groups) == 1
        assert len(req_groups[0].tasks) == 2
        assert len(epic_groups) == 1
        assert len(epic_groups[0].tasks) == 1
        assert len(standalone_groups) == 1
        assert len(standalone_groups[0].tasks) == 1

    def test_create_groups_empty(self):
        """Test create_groups with empty list."""
        engine = TaskGroupingEngine()
        
        groups = engine.create_groups(MagicMock(), [])
        
        assert len(groups) == 0

    def test_create_groups_o_n_complexity(self):
        """Test that grouping is O(n) by handling large lists efficiently."""
        engine = TaskGroupingEngine()
        
        # Create 1000 tasks with same requirement
        req_id = uuid4()
        tasks = [
            create_mock_task(task_number=i, requirement_id=str(req_id))
            for i in range(1000)
        ]
        
        # This should complete quickly if O(n)
        groups = engine.group_by_requirement(tasks)
        
        assert len(groups) == 1
        assert len(groups[req_id].tasks) == 1000
