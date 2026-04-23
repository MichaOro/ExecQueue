import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from execqueue.scheduler.runner import get_next_queued_task


class TestTaskLocking:
    """Tests for task locking mechanism."""

    def test_task_locked_on_fetch(self, db_session):
        """Test: Task is locked when fetched."""
        from execqueue.models.task import Task
        
        task = Task(
            source_type="requirement",
            source_id=700,
            title="Lock Test Task",
            prompt="Prompt",
            status="queued",
            is_test=True,
        )
        db_session.add(task)
        db_session.commit()
        
        fetched = get_next_queued_task(db_session)
        
        assert fetched is not None
        assert fetched.locked_by is not None
        assert fetched.locked_at is not None

    def test_locked_task_not_fetched_by_another_worker(self, db_session):
        """Test: Locked task is not fetched by another worker."""
        # Create and lock a task
        from execqueue.models.task import Task
        from datetime import datetime, timezone
        
        task = Task(
            source_type="requirement",
            source_id=800,
            title="Locked Task",
            prompt="Prompt",
            status="queued",
            is_test=True,
        )
        db_session.add(task)
        db_session.commit()
        
        task.locked_at = datetime.now(timezone.utc)
        task.locked_by = "worker-1"
        db_session.add(task)
        db_session.commit()
        
        with patch("execqueue.scheduler.runner.WORKER_INSTANCE_ID", "worker-2"):
            fetched_task = get_next_queued_task(db_session)
        
        # Should not fetch the locked task
        assert fetched_task is None or fetched_task.id != task.id

    def test_expired_lock_is_fetched(self, db_session):
        """Test: Expired lock is fetched by another worker."""
        from execqueue.models.task import Task
        from datetime import datetime, timezone, timedelta
        
        task = Task(
            source_type="requirement",
            source_id=801,
            title="Expired Lock Task",
            prompt="Prompt",
            status="queued",
            is_test=True,
        )
        db_session.add(task)
        db_session.commit()
        
        task.locked_at = datetime.now(timezone.utc) - timedelta(seconds=400)
        task.locked_by = "worker-1"
        db_session.add(task)
        db_session.commit()
        
        with patch("execqueue.scheduler.runner.WORKER_INSTANCE_ID", "worker-2"):
            fetched_task = get_next_queued_task(db_session)
        
        assert fetched_task is not None
        assert fetched_task.locked_by == "worker-2"

    def test_lock_timeout_configurable(self, db_session, monkeypatch):
        """Test: Lock timeout is configurable."""
        monkeypatch.setenv("WORKER_LOCK_TIMEOUT_SECONDS", "60")
        
        from execqueue.models.task import Task
        from datetime import datetime, timezone, timedelta
        
        task = Task(
            source_type="requirement",
            source_id=802,
            title="Config Timeout Task",
            prompt="Prompt",
            status="queued",
            is_test=True,
        )
        db_session.add(task)
        db_session.commit()
        
        task.locked_at = datetime.now(timezone.utc) - timedelta(seconds=61)
        task.locked_by = "worker-1"
        db_session.add(task)
        db_session.commit()
        
        with patch("execqueue.scheduler.runner.WORKER_INSTANCE_ID", "worker-2"):
            fetched_task = get_next_queued_task(db_session)
        
        assert fetched_task is not None
        assert fetched_task.locked_by == "worker-2"

    def test_concurrent_lock_prevention(self, db_session):
        """Test: Only one worker can lock a task concurrently."""
        from concurrent.futures import ThreadPoolExecutor
        from execqueue.models.task import Task
        from sqlmodel import Session
        from execqueue.db.engine import engine
        
        task = Task(
            source_type="requirement",
            source_id=803,
            title="Concurrent Lock Task",
            prompt="Prompt",
            status="queued",
            is_test=True,
        )
        db_session.add(task)
        db_session.commit()
        
        def try_lock(worker_id):
            with Session(engine) as local_session:
                with patch("execqueue.scheduler.runner.WORKER_INSTANCE_ID", worker_id):
                    fetched = get_next_queued_task(local_session)
                    return fetched.id if fetched else None
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(try_lock, ["w1", "w2", "w3", "w4", "w5"]))
        
        locked_count = sum(1 for r in results if r is not None)
        assert locked_count == 1
        
        locked_ids = [r for r in results if r is not None]
        assert len(set(locked_ids)) == 1
