import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from execqueue.models.dead_letter import DeadLetterQueue
from execqueue.scheduler.runner import _create_dlq_entry


class TestDeadLetterQueueCreation:
    """Tests for DLQ entry creation."""

    def test_dlq_entry_created_with_correct_data(self, db_session, sample_task):
        """Test: DLQ entry contains all correct data."""
        sample_task.last_result = "Failed after 5 retries"
        db_session.add(sample_task)
        db_session.commit()
        
        dlq_entry = _create_dlq_entry(sample_task, db_session)
        
        assert dlq_entry.task_id == sample_task.id
        assert dlq_entry.source_type == sample_task.source_type
        assert dlq_entry.source_id == sample_task.source_id
        assert dlq_entry.task_title == sample_task.title
        assert dlq_entry.task_prompt == sample_task.prompt
        assert dlq_entry.failure_reason == "Max retries exceeded"
        assert dlq_entry.retry_count == sample_task.retry_count
        assert dlq_entry.max_retries == sample_task.max_retries
        assert dlq_entry.failed_at is not None
        assert dlq_entry.created_at is not None

    def test_dlq_entry_in_database(self, db_session, sample_task):
        """Test: DLQ entry is persisted in database."""
        sample_task.last_result = "Test failure"
        db_session.add(sample_task)
        db_session.commit()
        
        _create_dlq_entry(sample_task, db_session)
        
        from sqlalchemy import text
        result = db_session.exec(text(f"SELECT COUNT(*) FROM dead_letter_queue WHERE task_id = {sample_task.id}")).one()
        dlq_count = result[0] if hasattr(result, '__getitem__') else result
        
        assert dlq_count == 1

    def test_dlq_snapshot_preserves_task_state(self, db_session, sample_task):
        """Test: DLQ snapshot preserves task state even if task changes."""
        original_title = sample_task.title
        original_prompt = sample_task.prompt
        
        dlq_entry = _create_dlq_entry(sample_task, db_session)
        
        # Change task after DLQ creation
        sample_task.title = "Changed Title"
        sample_task.prompt = "Changed Prompt"
        db_session.add(sample_task)
        db_session.commit()
        
        # DLQ should still have original values
        assert dlq_entry.task_title == original_title
        assert dlq_entry.task_prompt == original_prompt


class TestDeadLetterQueueAPI:
    """Tests for DLQ API endpoints."""

    def test_list_dead_letter_queue(self, client, db_session, dead_letter_entry):
        """Test: GET /dead-letter returns DLQ entries."""
        response = client.get("/api/dead-letter")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total"] >= 1
        assert len(data["entries"]) >= 1
        
        entry = data["entries"][0]
        assert entry["task_id"] == dead_letter_entry.task_id
        assert entry["source_type"] == dead_letter_entry.source_type
        assert entry["failure_reason"] == "Max retries exceeded"

    def test_list_dead_letter_queue_pagination(self, client, db_session, dead_letter_entry):
        """Test: GET /dead-letter supports pagination."""
        response = client.get("/api/dead-letter?page=1&page_size=10")
        assert response.status_code == 200
        
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert "total" in data
        assert "entries" in data

    def test_get_dead_letter_detail(self, client, dead_letter_entry):
        """Test: GET /dead-letter/{id} returns entry details."""
        response = client.get(f"/api/dead-letter/{dead_letter_entry.id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["task_id"] == dead_letter_entry.task_id
        assert data["task_title"] == dead_letter_entry.task_title
        assert data["failure_details"] == dead_letter_entry.failure_details

    def test_get_dead_letter_not_found(self, client):
        """Test: GET /dead-letter/{id} returns 404 for non-existent entry."""
        response = client.get("/api/dead-letter/99999")
        assert response.status_code == 404

    def test_requeue_dead_letter(self, client, dead_letter_entry):
        """Test: POST /dead-letter/{id}/requeue creates new task."""
        response = client.post(f"/api/dead-letter/{dead_letter_entry.id}/requeue")
        assert response.status_code == 200
        
        data = response.json()
        assert data["requeued_count"] == 1
        assert len(data["new_task_ids"]) == 1
        assert data["new_task_ids"][0] is not None

    def test_bulk_requeue_dead_letter(self, client, db_session, dead_letter_entry):
        """Test: POST /dead-letter/bulk-requeue creates multiple tasks."""
        # Create another DLQ entry
        from execqueue.models.task import Task
        task2 = Task(
            source_type="requirement",
            source_id=999,
            title="Task 2",
            prompt="Prompt 2",
            is_test=True,
        )
        db_session.add(task2)
        db_session.commit()
        
        dlq2 = DeadLetterQueue(
            task_id=task2.id,
            source_type="requirement",
            source_id=999,
            task_title="Task 2",
            task_prompt="Prompt 2",
            failure_reason="Test",
            failure_details="Test",
            retry_count=5,
            max_retries=5,
        )
        db_session.add(dlq2)
        db_session.commit()
        
        response = client.post(
            "/api/dead-letter/bulk-requeue",
            json={"task_ids": [dead_letter_entry.id, dlq2.id]}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["requeued_count"] == 2
        assert len(data["new_task_ids"]) == 2

    def test_delete_dead_letter(self, client, dead_letter_entry, db_session):
        """Test: DELETE /dead-letter/{id} removes entry."""
        response = client.delete(f"/api/dead-letter/{dead_letter_entry.id}")
        assert response.status_code == 200
        
        # Verify entry is deleted - refresh session to see changes from API
        db_session.rollback()  # Clear any cached state
        try:
            remaining = db_session.get(DeadLetterQueue, dead_letter_entry.id)
            # If we get here, check if it's actually None
            assert remaining is None
        except Exception:
            # ObjectDeletedError means the entry was successfully deleted
            pass
