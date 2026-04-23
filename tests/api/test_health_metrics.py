import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from execqueue.main import app
from execqueue.api.health import update_worker_state, get_worker_state


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def healthy_worker():
    """Set up healthy worker state."""
    update_worker_state(
        started_at=1000.0,
        instance_id="test-worker-1",
        is_running=True,
        last_task_at="2026-04-23T10:00:00Z",
        tasks_processed=10,
        tasks_failed=1,
    )
    yield
    # Reset after test
    update_worker_state(is_running=False)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_healthy(self, client, healthy_worker):
        """Test: /health returns 200 when worker is healthy."""
        response = client.get("/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["worker"]["running"] is True
        assert data["worker"]["instance_id"] == "test-worker-1"
        assert data["worker"]["tasks_processed"] == 10
        assert data["database"]["connected"] is True

    def test_health_unhealthy_not_running(self, client):
        """Test: /health returns 503 when worker is not running."""
        update_worker_state(is_running=False)
        response = client.get("/api/health")
        assert response.status_code == 503

    def test_ready_ready(self, client, healthy_worker):
        """Test: /ready returns 200 when worker is ready."""
        with patch("execqueue.api.health.is_scheduler_enabled", return_value=True):
            response = client.get("/api/ready")
            assert response.status_code == 200
            
            data = response.json()
            assert data["ready"] is True
            assert data["can_accept_tasks"] is True
            assert data["scheduler_enabled"] is True

    def test_ready_not_ready_scheduler_disabled(self, client, healthy_worker):
        """Test: /ready returns 503 when scheduler is disabled."""
        with patch("execqueue.api.health.is_scheduler_enabled", return_value=False):
            response = client.get("/api/ready")
            assert response.status_code == 503

    def test_version(self, client):
        """Test: /version returns version info."""
        response = client.get("/api/version")
        assert response.status_code == 200
        
        data = response.json()
        assert "version" in data
        assert "instance_id" in data
        assert "timestamp" in data


class TestMetricsEndpoint:
    """Tests for metrics endpoint."""

    def test_metrics_returns_prometheus_format(self, client):
        """Test: /metrics returns Prometheus format."""
        response = client.get("/api/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        
        content = response.text
        assert "execqueue_tasks_processed_total" in content
        assert "execqueue_task_duration_seconds" in content
        assert "execqueue_queue_length" in content

    def test_metrics_contains_expected_counters(self, client):
        """Test: /metrics contains expected metric names."""
        response = client.get("/api/metrics")
        content = response.text
        
        expected_metrics = [
            "execqueue_tasks_processed_total",
            "execqueue_task_retries_total",
            "execqueue_task_duration_seconds",
            "execqueue_queue_length",
            "execqueue_errors_total",
            "execqueue_worker_count",
        ]
        
        for metric in expected_metrics:
            assert metric in content
