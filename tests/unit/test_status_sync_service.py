"""
Tests for Status Synchronization Service.

Tests the status synchronization between Tasks, WorkPackages, and Requirements
according to the Kanban workflow.
"""

import pytest
from sqlmodel import Session
from execqueue.services.status_sync_service import (
    validate_status_transition,
    calculate_requirement_status,
    calculate_work_package_status,
    get_kanban_summary,
    StatusValidationError,
)
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task


class TestStatusValidation:
    """Tests for status transition validation."""

    def test_valid_transition_backlog_to_in_progress(self):
        """Test: backlog → in_progress is valid."""
        assert validate_status_transition("backlog", "in_progress") is True

    def test_valid_transition_in_progress_to_review(self):
        """Test: in_progress → review is valid."""
        assert validate_status_transition("in_progress", "review") is True

    def test_valid_transition_review_to_done(self):
        """Test: review → done is valid."""
        assert validate_status_transition("review", "done") is True

    def test_valid_transition_same_status(self):
        """Test: Same status is always valid."""
        assert validate_status_transition("backlog", "backlog") is True
        assert validate_status_transition("done", "done") is True

    def test_invalid_transition_backlog_to_done(self):
        """Test: backlog → done is invalid (must go through in_progress, review)."""
        with pytest.raises(StatusValidationError, match="Ungültiger Status-Übergang"):
            validate_status_transition("backlog", "done")

    def test_invalid_transition_done_to_in_progress(self):
        """Test: done → in_progress is invalid."""
        with pytest.raises(StatusValidationError, match="Ungültiger Status-Übergang"):
            validate_status_transition("done", "in_progress")

    def test_invalid_transition_to_unknown_status(self):
        """Test: Transition to unknown status raises error."""
        with pytest.raises(StatusValidationError):
            validate_status_transition("backlog", "unknown_status")


class TestRequirementStatusCalculation:
    """Tests for requirement status calculation based on work packages."""

    def test_requirement_done_when_all_wps_done(self, db_session):
        """Test: Requirement is done when all WorkPackages are done."""
        req = Requirement(
            title="Test Requirement",
            description="Test description",
            markdown_content="Test content",
            queue_status="backlog",
            type="artifact",
            is_test=True,
        )
        db_session.add(req)
        db_session.commit()
        db_session.refresh(req)
        
        wps = [
            WorkPackage(requirement_id=req.id, title="WP1", queue_status="done", is_test=True),
            WorkPackage(requirement_id=req.id, title="WP2", queue_status="done", is_test=True),
        ]
        db_session.add_all(wps)
        db_session.commit()

        status = calculate_requirement_status(req, db_session)
        assert status == "done"

    def test_requirement_in_progress_when_some_wp_in_progress(self, db_session):
        """Test: Requirement is in_progress when at least one WP is in_progress."""
        req = Requirement(
            title="Test Requirement",
            description="Test description",
            markdown_content="Test content",
            queue_status="backlog",
            type="artifact",
            is_test=True,
        )
        db_session.add(req)
        db_session.commit()
        db_session.refresh(req)
        
        wps = [
            WorkPackage(requirement_id=req.id, title="WP1", queue_status="backlog", is_test=True),
            WorkPackage(requirement_id=req.id, title="WP2", queue_status="in_progress", is_test=True),
        ]
        db_session.add_all(wps)
        db_session.commit()

        status = calculate_requirement_status(req, db_session)
        assert status == "in_progress"

    def test_requirement_backlog_when_all_wps_backlog(self, db_session):
        """Test: Requirement is backlog when all WorkPackages are backlog."""
        req = Requirement(
            title="Test Requirement",
            description="Test description",
            markdown_content="Test content",
            queue_status="backlog",
            type="artifact",
            is_test=True,
        )
        db_session.add(req)
        db_session.commit()
        db_session.refresh(req)
        
        wps = [
            WorkPackage(requirement_id=req.id, title="WP1", queue_status="backlog", is_test=True),
            WorkPackage(requirement_id=req.id, title="WP2", queue_status="backlog", is_test=True),
        ]
        db_session.add_all(wps)
        db_session.commit()

        status = calculate_requirement_status(req, db_session)
        assert status == "backlog"

    def test_requirement_trash_when_any_wp_trash(self, db_session):
        """Test: Requirement is trash when at least one WP is trash."""
        req = Requirement(
            title="Test Requirement",
            description="Test description",
            markdown_content="Test content",
            queue_status="backlog",
            type="artifact",
            is_test=True,
        )
        db_session.add(req)
        db_session.commit()
        db_session.refresh(req)
        
        wps = [
            WorkPackage(requirement_id=req.id, title="WP1", queue_status="done", is_test=True),
            WorkPackage(requirement_id=req.id, title="WP2", queue_status="trash", is_test=True),
        ]
        db_session.add_all(wps)
        db_session.commit()

        status = calculate_requirement_status(req, db_session)
        assert status == "trash"

    def test_requirement_no_work_packages(self, db_session):
        """Test: Returns current status when no WorkPackages exist."""
        req = Requirement(
            title="Test Requirement",
            description="Test description",
            markdown_content="Test content",
            queue_status="backlog",
            type="artifact",
            is_test=True,
        )
        db_session.add(req)
        db_session.commit()
        db_session.refresh(req)
        
        status = calculate_requirement_status(req, db_session)
        assert status == "backlog"


class TestWorkPackageStatusCalculation:
    """Tests for work package status calculation based on tasks."""

    def test_wp_done_when_all_tasks_done(self, db_session):
        """Test: WorkPackage is done when all Tasks are done."""
        wp = WorkPackage(
            requirement_id=1,
            title="Test WP",
            queue_status="backlog",
            is_test=True,
        )
        db_session.add(wp)
        db_session.commit()
        db_session.refresh(wp)
        
        tasks = [
            Task(
                source_type="work_package",
                source_id=wp.id,
                title="Task1",
                prompt="Test prompt 1",
                queue_status="done",
                is_test=True,
            ),
            Task(
                source_type="work_package",
                source_id=wp.id,
                title="Task2",
                prompt="Test prompt 2",
                queue_status="done",
                is_test=True,
            ),
        ]
        db_session.add_all(tasks)
        db_session.commit()

        status = calculate_work_package_status(wp, db_session)
        assert status == "done"

    def test_wp_in_progress_when_some_task_in_progress(self, db_session):
        """Test: WorkPackage is in_progress when at least one Task is in_progress."""
        wp = WorkPackage(
            requirement_id=1,
            title="Test WP",
            queue_status="backlog",
            is_test=True,
        )
        db_session.add(wp)
        db_session.commit()
        db_session.refresh(wp)
        
        tasks = [
            Task(
                source_type="work_package",
                source_id=wp.id,
                title="Task1",
                prompt="Test prompt 1",
                queue_status="backlog",
                is_test=True,
            ),
            Task(
                source_type="work_package",
                source_id=wp.id,
                title="Task2",
                prompt="Test prompt 2",
                queue_status="in_progress",
                is_test=True,
            ),
        ]
        db_session.add_all(tasks)
        db_session.commit()

        status = calculate_work_package_status(wp, db_session)
        assert status == "in_progress"

    def test_wp_trash_when_any_task_trash(self, db_session):
        """Test: WorkPackage is trash when at least one Task is trash."""
        wp = WorkPackage(
            requirement_id=1,
            title="Test WP",
            queue_status="backlog",
            is_test=True,
        )
        db_session.add(wp)
        db_session.commit()
        db_session.refresh(wp)
        
        tasks = [
            Task(
                source_type="work_package",
                source_id=wp.id,
                title="Task1",
                prompt="Test prompt 1",
                queue_status="done",
                is_test=True,
            ),
            Task(
                source_type="work_package",
                source_id=wp.id,
                title="Task2",
                prompt="Test prompt 2",
                queue_status="trash",
                is_test=True,
            ),
        ]
        db_session.add_all(tasks)
        db_session.commit()

        status = calculate_work_package_status(wp, db_session)
        assert status == "trash"


class TestKanbanSummary:
    """Tests for Kanban board summary."""

    def test_kanban_summary_empty(self, db_session):
        """Test: Empty summary when no data."""
        summary = get_kanban_summary(db_session, is_test=True)
        
        assert "tasks" in summary
        assert "work_packages" in summary
        assert "requirements" in summary

    def test_kanban_summary_with_data(self, db_session):
        """Test: Summary counts tasks, WPs, and requirements by status."""
        req = Requirement(
            title="Test Requirement",
            description="Test description",
            markdown_content="Test content",
            queue_status="in_progress",
            type="artifact",
            is_test=True,
        )
        db_session.add(req)
        db_session.commit()
        db_session.refresh(req)
        
        wp = WorkPackage(
            requirement_id=req.id,
            title="WP1",
            queue_status="in_progress",
            is_test=True,
        )
        db_session.add(wp)
        db_session.commit()

        task = Task(
            source_type="work_package",
            source_id=wp.id,
            title="Task1",
            prompt="Test prompt",
            queue_status="backlog",
            is_test=True,
        )
        db_session.add(task)
        db_session.commit()

        summary = get_kanban_summary(db_session, is_test=True)
        
        assert isinstance(summary["tasks"], dict)
        assert isinstance(summary["work_packages"], dict)
        assert isinstance(summary["requirements"], dict)
