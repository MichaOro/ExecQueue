"""
Integration tests for OpenCode ACP integration.

These tests require a running OpenCode ACP server and test the full integration
with real sessions, unlike unit tests which mock the CLI.
"""

import pytest
import subprocess
import time
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from execqueue.workers.opencode_adapter import (
    OpenCodeACPClient,
    OpenCodeSessionLostError,
    OpenCodeTimeoutError,
    OpenCodeConnectionError,
    OpenCodeConfigurationError,
)
from execqueue.services.opencode_session_service import OpenCodeSessionService
from execqueue.models.task import Task, OpenCodeSessionStatus


class TestACPClientIntegration:
    """Integration tests for OpenCodeACPClient with real CLI."""
    
    @pytest.fixture
    def test_project_dir(self, tmp_path):
        """Create a minimal test project directory."""
        # Create a simple Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("# Test project\n")
        
        # Create a simple README
        readme = tmp_path / "README.md"
        readme.write_text("# Test Project\n")
        
        return str(tmp_path)
    
    def test_client_can_connect(self):
        """Test: Client can be initialized and CLI is available."""
        client = OpenCodeACPClient(
            acp_url="http://localhost:8765",
            password=os.getenv("OPENCODE_SERVER_PASSWORD", "test")
        )
        
        assert client.acp_url == "http://localhost:8765"
        assert client.password is not None
    
    @pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run"
    )
    def test_start_and_export_session(self, test_project_dir):
        """Test: Full session lifecycle with real ACP server."""
        client = OpenCodeACPClient(
            acp_url="http://localhost:8765",
            password=os.getenv("OPENCODE_SERVER_PASSWORD", "test"),
            timeout=60
        )
        
        # Start session
        session_id = client.start_session(
            prompt="echo 'Hello from OpenCode'",
            cwd=test_project_dir,
            title="Test Session"
        )
        
        assert session_id is not None
        assert len(session_id) > 0
        
        # Wait for completion (max 30 seconds)
        max_wait = 30
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                status = client.get_session_status(session_id)
                if status.get("status") in ["completed", "success"]:
                    break
                time.sleep(2)
            except (OpenCodeConnectionError, OpenCodeSessionLostError):
                time.sleep(2)
                continue
        
        # Export result
        result = client.export_session(session_id)
        
        assert result is not None
        assert "output" in result or "raw_output" in result


class TestSessionServiceIntegration:
    """Integration tests for OpenCodeSessionService."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        with patch("sqlmodel.Session") as mock:
            yield mock
    
    def test_service_initialization(self):
        """Test: Service can be initialized with ACP client."""
        client = OpenCodeACPClient()
        service = OpenCodeSessionService(acp_client=client)
        
        assert service.client is not None
    
    @pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run"
    )
    def test_create_and_monitor_session(self, mock_session, test_project_dir):
        """Test: Create and monitor session via service."""
        client = OpenCodeACPClient(
            acp_url="http://localhost:8765",
            password=os.getenv("OPENCODE_SERVER_PASSWORD", "test")
        )
        service = OpenCodeSessionService(acp_client=client)
        
        # Create mock task
        task = Task(
            source_type="test",
            source_id=1,
            title="Test Task",
            prompt="echo 'Test'",
            opencode_project_path=test_project_dir,
            opencode_status=OpenCodeSessionStatus.PENDING
        )
        
        # Mock database operations
        mock_session.add = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.refresh = MagicMock()
        
        # Create session (would normally call ACP)
        with patch.object(client, 'start_session', return_value="test-session-123"):
            created_task = service.create_session(mock_session, task)
            
            assert created_task.opencode_session_id == "test-session-123"
            assert created_task.opencode_status == OpenCodeSessionStatus.RUNNING


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""
    
    def test_invalid_session_id_raises_error(self):
        """Test: Invalid session ID raises OpenCodeSessionLostError."""
        client = OpenCodeACPClient(
            acp_url="http://localhost:8765",
            password="test"
        )
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "session not found"
            mock_run.return_value = mock_result
            
            with pytest.raises(OpenCodeSessionLostError, match="Session lost"):
                client.get_session_status("invalid-session-id-12345")
    
    def test_cli_timeout_raises_error(self):
        """Test: CLI timeout raises OpenCodeTimeoutError."""
        from subprocess import TimeoutExpired
        
        client = OpenCodeACPClient(
            acp_url="http://localhost:8765",
            password="test"
        )
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.side_effect = TimeoutExpired(cmd="opencode", timeout=30)
            
            with pytest.raises(OpenCodeTimeoutError, match="timed out"):
                client.start_session(prompt="Test", cwd="/tmp")
    
    def test_missing_cli_raises_error(self):
        """Test: Missing opencode CLI raises configuration error."""
        client = OpenCodeACPClient(
            acp_url="http://localhost:8765",
            password="test"
        )
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("opencode")
            
            with pytest.raises(OpenCodeConfigurationError, match="not found"):
                client.start_session(prompt="Test", cwd="/tmp")


class TestRetryLogicIntegration:
    """Integration tests for retry logic."""
    
    def test_retry_on_connection_error(self):
        """Test: Client retries on connection errors."""
        from execqueue.workers.opencode_adapter import OpenCodeConnectionError
        
        client = OpenCodeACPClient(
            acp_url="http://localhost:8765",
            password="test"
        )
        
        call_count = 0
        
        def failing_command(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stderr = "Connection failed"
                return mock_result
            else:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = '{"session_id": "test-123"}'
                return mock_result
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.side_effect = failing_command
            
            # Should succeed after 2 retries
            result = client.start_session(prompt="Test", cwd="/tmp")
            
            assert call_count == 3  # Initial + 2 retries
            assert result == "test-123"
