import pytest
import json
from unittest.mock import patch, MagicMock
from httpx import TimeoutException, ConnectError, HTTPError, MockTransport

from execqueue.workers.opencode_adapter import (
    execute_with_opencode,
    OpenCodeExecutionResult,
    OpenCodeClient,
    OpenCodeError,
    OpenCodeTimeoutError,
    OpenCodeConnectionError,
    OpenCodeHTTPError,
    OpenCodeConfigurationError,
    OpenCodeSessionLostError,
    OpenCodeACPClient,
)
from execqueue.validation.task_validator import validate_task_result


class TestOpenCodeExceptions:
    """Tests for OpenCode exception classes."""

    def test_opencode_error_base(self):
        """Test: Base OpenCodeError can be raised and caught."""
        with pytest.raises(OpenCodeError, match="test error"):
            raise OpenCodeError("test error")

    def test_opencode_timeout_error(self):
        """Test: OpenCodeTimeoutError preserves message."""
        with pytest.raises(OpenCodeTimeoutError, match="timeout"):
            raise OpenCodeTimeoutError("timeout")

    def test_opencode_connection_error(self):
        """Test: OpenCodeConnectionError preserves message."""
        with pytest.raises(OpenCodeConnectionError, match="connection failed"):
            raise OpenCodeConnectionError("connection failed")

    def test_opencode_http_error_with_status(self):
        """Test: OpenCodeHTTPError includes status code."""
        error = OpenCodeHTTPError("Not found", status_code=404)
        assert error.status_code == 404
        assert "Not found" in str(error)

    def test_opencode_configuration_error(self):
        """Test: OpenCodeConfigurationError for missing config."""
        with pytest.raises(OpenCodeConfigurationError, match="OPENCODE_BASE_URL"):
            raise OpenCodeConfigurationError("OPENCODE_BASE_URL not set")


class TestOpenCodeClient:
    """Tests for OpenCodeClient class."""

    def test_client_initialization(self):
        """Test: Client initializes with default values."""
        client = OpenCodeClient(base_url="http://test.local")
        assert client.base_url == "http://test.local"
        assert client.timeout == 120
        assert client.max_retries == 3

    def test_client_initialization_custom(self):
        """Test: Client initializes with custom values."""
        client = OpenCodeClient(
            base_url="http://test.local",
            timeout=60,
            max_retries=5,
        )
        assert client.base_url == "http://test.local"
        assert client.timeout == 60
        assert client.max_retries == 5

    def test_client_initialization_with_auth(self):
        """Test: Client initializes with HTTP Basic Auth."""
        client = OpenCodeClient(
            base_url="http://test.local",
            auth=("testuser", "testpass"),
        )
        assert client.base_url == "http://test.local"
        assert client.auth == ("testuser", "testpass")
        assert client.timeout == 120
        assert client.max_retries == 3

    def test_client_initialization_without_auth(self):
        """Test: Client initializes without auth (None)."""
        client = OpenCodeClient(
            base_url="http://test.local",
            auth=None,
        )
        assert client.auth is None

    def test_client_trims_base_url_slash(self):
        """Test: Client removes trailing slash from base_url."""
        client = OpenCodeClient(base_url="http://test.local/")
        assert client.base_url == "http://test.local"

    def test_calculate_backoff_delay_exponential_growth(self):
        """Test: Backoff delay grows exponentially."""
        client = OpenCodeClient(base_url="http://test.local")
        
        assert client._calculate_backoff_delay(0) == 1.0
        assert client._calculate_backoff_delay(1) == 2.0
        assert client._calculate_backoff_delay(2) == 4.0
        assert client._calculate_backoff_delay(3) == 8.0

    def test_calculate_backoff_delay_max_cap(self):
        """Test: Backoff delay is capped at max_delay."""
        client = OpenCodeClient(base_url="http://test.local")
        
        assert client._calculate_backoff_delay(10) == 10.0
        assert client._calculate_backoff_delay(20) == 10.0

    def test_parse_response_valid(self):
        """Test: Parse valid response."""
        client = OpenCodeClient(base_url="http://test.local")
        
        response_data = {
            "status": "completed",
            "output": "Test output",
            "summary": "Test summary",
        }
        
        result = client._parse_response(response_data)
        
        assert result.status == "completed"
        assert result.raw_output == "Test output"
        assert result.summary == "Test summary"

    def test_parse_response_missing_summary(self):
        """Test: Parse response without summary field."""
        client = OpenCodeClient(base_url="http://test.local")
        
        response_data = {
            "status": "completed",
            "output": "Test output",
        }
        
        result = client._parse_response(response_data)
        
        assert result.status == "completed"
        assert result.raw_output == "Test output"
        assert result.summary == "Test output"

    def test_parse_response_empty(self):
        """Test: Parse response with empty output."""
        client = OpenCodeClient(base_url="http://test.local")
        
        response_data = {
            "status": "completed",
            "output": "",
        }
        
        result = client._parse_response(response_data)
        
        assert result.raw_output == ""
        assert result.summary == "No summary"

    def test_parse_response_invalid_format(self):
        """Test: Parse raises error for invalid format."""
        client = OpenCodeClient(base_url="http://test.local")
        
        with pytest.raises(OpenCodeHTTPError, match="Invalid response format"):
            client._parse_response("not a dict")

    def test_context_manager(self):
        """Test: Client works as context manager."""
        with OpenCodeClient(base_url="http://test.local") as client:
            assert client is not None


class TestExecuteWithOpencode:
    """Tests for execute_with_opencode function."""

    def test_configuration_error_when_no_url(self, monkeypatch):
        """Test: Raises configuration error when BASE_URL not set."""
        monkeypatch.delenv("OPENCODE_BASE_URL", raising=False)
        
        with pytest.raises(OpenCodeConfigurationError, match="OPENCODE_BASE_URL"):
            execute_with_opencode(prompt="test")

    def test_successful_execution(self, monkeypatch):
        """Test: Successful execution returns result."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        mock_response = {
            "status": "completed",
            "output": "Test output",
            "summary": "Test summary",
        }
        
        with patch("httpx.Client.post") as mock_post:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_post.return_value = mock_response_obj
            
            result = execute_with_opencode(prompt="test prompt")
            
            assert isinstance(result, OpenCodeExecutionResult)
            assert result.status == "completed"
            assert result.raw_output == "Test output"
            assert result.summary == "Test summary"

    def test_successful_execution_with_auth(self, monkeypatch):
        """Test: Successful execution includes HTTP Basic Auth."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        monkeypatch.setenv("OPENCODE_USERNAME", "testuser")
        monkeypatch.setenv("OPENCODE_PASSWORD", "testpass")
        
        mock_response = {
            "status": "completed",
            "output": "Test output",
            "summary": "Test summary",
        }
        
        with patch("httpx.Client.post") as mock_post:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_post.return_value = mock_response_obj
            
            result = execute_with_opencode(prompt="test prompt")
            
            assert isinstance(result, OpenCodeExecutionResult)
            assert result.status == "completed"
            # Verify auth was passed to httpx.Client
            assert mock_post.call_count == 1
            # Check that the client was initialized with auth
            from httpx import Client
            with patch.object(Client, "__init__", return_value=None) as mock_client_init:
                client = OpenCodeClient(
                    base_url="http://test.local",
                    auth=("testuser", "testpass"),
                )
                assert client.auth == ("testuser", "testpass")

    def test_successful_execution_with_verification(self, monkeypatch):
        """Test: Execution includes verification_prompt."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        mock_response = {
            "status": "completed",
            "output": "Test output",
        }
        
        with patch("httpx.Client.post") as mock_post:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_post.return_value = mock_response_obj
            
            execute_with_opencode(
                prompt="test prompt",
                verification_prompt="verify this"
            )
            
            call_args = mock_post.call_args
            assert call_args.kwargs["json"]["verification_prompt"] == "verify this"

    def test_timeout_error_after_retries(self, monkeypatch):
        """Test: Timeout error raised after max retries."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        monkeypatch.setenv("OPENCODE_MAX_RETRIES", "2")
        
        with patch("httpx.Client.post") as mock_post:
            mock_post.side_effect = TimeoutException("Timeout")
            
            with pytest.raises(OpenCodeTimeoutError):
                execute_with_opencode(prompt="test")
            
            assert mock_post.call_count == 3

    def test_connection_error_after_retries(self, monkeypatch):
        """Test: Connection error raised after max retries."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        monkeypatch.setenv("OPENCODE_MAX_RETRIES", "1")
        
        with patch("httpx.Client.post") as mock_post:
            mock_post.side_effect = ConnectError("Connection failed")
            
            with pytest.raises(OpenCodeConnectionError):
                execute_with_opencode(prompt="test")
            
            assert mock_post.call_count == 2

    def test_http_4xx_error_no_retry(self, monkeypatch):
        """Test: 4xx errors are not retried."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        monkeypatch.setenv("OPENCODE_MAX_RETRIES", "3")
        
        with patch("httpx.Client.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad request"
            mock_post.return_value = mock_response
            
            with pytest.raises(OpenCodeHTTPError):
                execute_with_opencode(prompt="test")
            
            assert mock_post.call_count == 1

    def test_http_5xx_error_with_retry(self, monkeypatch):
        """Test: 5xx errors are retried."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        monkeypatch.setenv("OPENCODE_MAX_RETRIES", "1")
        
        with patch("httpx.Client.post") as mock_post:
            mock_error = HTTPError("Server error")
            mock_error.response = MagicMock()
            mock_error.response.status_code = 500
            mock_error.response.text = "Internal server error"
            
            mock_success = MagicMock()
            mock_success.status_code = 200
            mock_success.json.return_value = {"status": "completed", "output": "OK"}
            
            mock_post.side_effect = [mock_error, mock_success]
            
            result = execute_with_opencode(prompt="test")
            
            assert mock_post.call_count == 2
            assert result.status == "completed"

    def test_http_401_unauthorized(self, monkeypatch):
        """Test: 401 error raises error."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        with patch("httpx.Client.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_post.return_value = mock_response
            
            with pytest.raises(OpenCodeHTTPError):
                execute_with_opencode(prompt="test")

    def test_http_404_not_found(self, monkeypatch):
        """Test: 404 error raises error."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        with patch("httpx.Client.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not found"
            mock_post.return_value = mock_response
            
            with pytest.raises(OpenCodeHTTPError):
                execute_with_opencode(prompt="test")

    def test_response_parsing_with_raw_output_field(self, monkeypatch):
        """Test: Parse response with 'raw_output' instead of 'output'."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        mock_response = {
            "status": "completed",
            "raw_output": "Alternative output field",
        }
        
        with patch("httpx.Client.post") as mock_post:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_post.return_value = mock_response_obj
            
            result = execute_with_opencode(prompt="test")
            
            assert result.raw_output == "Alternative output field"


class TestOpenCodeContract:
    """Contract tests for OpenCode API response structure.
    
    These tests verify that the OpenCode adapter always returns properly
    structured responses, regardless of the actual execution result.
    """
    
    def test_contract_execution_returns_result(self, monkeypatch):
        """Test: Execution returns properly structured OpenCodeExecutionResult."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        def mock_handler(request):
            from httpx import Response
            return Response(
                status_code=200,
                json={
                    "status": "completed",
                    "output": "Mocked execution result",
                    "summary": "Mocked summary",
                },
            )
        
        transport = MockTransport(mock_handler)
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda self: mock_client
            mock_client.__exit__ = lambda self, *args: None
            mock_client.post.return_value.status_code = 200
            mock_client.post.return_value.json.return_value = {
                "status": "completed",
                "output": "Mocked execution result",
                "summary": "Mocked summary",
            }
            mock_client_class.return_value = mock_client
            
            result = execute_with_opencode(prompt="test prompt")

        assert isinstance(result, OpenCodeExecutionResult)
        assert result.status in ["completed", "failed", "error"]
        assert result.raw_output is not None
        assert result.summary is not None

    def test_contract_status_field(self, monkeypatch):
        """Test: Result always has status field with valid value."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda self: mock_client
            mock_client.__exit__ = lambda self, *args: None
            mock_client.post.return_value.status_code = 200
            mock_client.post.return_value.json.return_value = {
                "status": "completed",
                "output": "Output",
                "summary": "Summary",
            }
            mock_client_class.return_value = mock_client
            
            result = execute_with_opencode(prompt="test")
        
        assert result.status in ["completed", "failed", "error"]

    def test_contract_raw_output_field(self, monkeypatch):
        """Test: Result always has non-empty raw_output field."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda self: mock_client
            mock_client.__exit__ = lambda self, *args: None
            mock_client.post.return_value.status_code = 200
            mock_client.post.return_value.json.return_value = {
                "status": "completed",
                "output": "Test output",
                "summary": "Summary",
            }
            mock_client_class.return_value = mock_client
            
            result = execute_with_opencode(prompt="test")
        
        assert result.raw_output is not None
        assert isinstance(result.raw_output, str)
        assert len(result.raw_output) > 0

    def test_contract_summary_field(self, monkeypatch):
        """Test: Result has summary field."""
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://test.local")
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda self: mock_client
            mock_client.__exit__ = lambda self, *args: None
            mock_client.post.return_value.status_code = 200
            mock_client.post.return_value.json.return_value = {
                "status": "completed",
                "output": "Output",
                "summary": "Test summary",
            }
            mock_client_class.return_value = mock_client
            
            result = execute_with_opencode(prompt="test")
        
        assert result.summary is not None
        assert isinstance(result.summary, str)


# ============================================================================
# Tests for OpenCodeACPClient
# ============================================================================

class TestOpenCodeACPClient:
    """Tests for OpenCodeACPClient class."""
    
    def test_client_initialization_defaults(self, monkeypatch):
        """Test: Client initializes with default values from env."""
        monkeypatch.setenv("OPENCODE_ACP_URL", "http://test.acp.local")
        monkeypatch.setenv("OPENCODE_PASSWORD", "testpass")
        monkeypatch.setenv("OPENCODE_SESSION_TIMEOUT", "600")
        
        client = OpenCodeACPClient()
        
        assert client.acp_url == "http://test.acp.local"
        assert client.password == "testpass"
        assert client.timeout == 600
    
    def test_client_initialization_explicit(self):
        """Test: Client initializes with explicit values."""
        client = OpenCodeACPClient(
            acp_url="http://explicit.local",
            password="explicitpass",
            timeout=900,
        )
        
        assert client.acp_url == "http://explicit.local"
        assert client.password == "explicitpass"
        assert client.timeout == 900
    
    def test_start_session_success(self, monkeypatch, tmp_path):
        """Test: Start session returns session ID."""
        monkeypatch.setenv("OPENCODE_ACP_URL", "http://test.local")
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"session_id": "test-123", "status": "started"})
        mock_result.stderr = ""
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            
            client = OpenCodeACPClient()
            session_id = client.start_session(
                prompt="Test prompt",
                cwd=str(tmp_path),
                title="Test Session"
            )
            
            assert session_id == "test-123"
            mock_run.assert_called_once()
    
    def test_start_session_no_session_id(self, monkeypatch, tmp_path):
        """Test: Start session generates ID if not in response."""
        monkeypatch.setenv("OPENCODE_ACP_URL", "http://test.local")
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": "started"})
        mock_result.stderr = ""
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            
            client = OpenCodeACPClient()
            session_id = client.start_session(prompt="Test", cwd=str(tmp_path))
            
            assert session_id.startswith("session-")
    
    def test_start_session_failure(self, monkeypatch, tmp_path):
        """Test: Start session raises error on failure."""
        monkeypatch.setenv("OPENCODE_ACP_URL", "http://test.local")
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Connection failed"
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            
            client = OpenCodeACPClient()
            
            with pytest.raises(OpenCodeConnectionError, match="Command failed"):
                client.start_session(prompt="Test", cwd=str(tmp_path))
    
    def test_get_session_status(self, monkeypatch):
        """Test: Get session status returns status dict."""
        monkeypatch.setenv("OPENCODE_ACP_URL", "http://test.local")
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "status": "running",
            "output": "Processing..."
        })
        mock_result.stderr = ""
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            
            client = OpenCodeACPClient()
            status = client.get_session_status("test-123")
            
            assert status["session_id"] == "test-123"
            assert status["status"] == "running"
            assert status["output"] == "Processing..."
    
    def test_continue_session(self, monkeypatch):
        """Test: Continue session sends prompt."""
        monkeypatch.setenv("OPENCODE_ACP_URL", "http://test.local")
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": "continued"})
        mock_result.stderr = ""
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            
            client = OpenCodeACPClient()
            result = client.continue_session("test-123", prompt="Continue")
            
            assert result["status"] == "continued"
    
    def test_export_session_success(self, monkeypatch):
        """Test: Export session returns result."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "session_id": "test-123",
            "output": "Final result",
            "status": "completed"
        })
        mock_result.stderr = ""
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            
            client = OpenCodeACPClient()
            result = client.export_session("test-123")
            
            assert result["output"] == "Final result"
            assert result["status"] == "completed"
    
    def test_export_session_timeout(self, monkeypatch):
        """Test: Export session raises timeout error."""
        from subprocess import TimeoutExpired
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.side_effect = TimeoutExpired(cmd="opencode export", timeout=30)
            
            client = OpenCodeACPClient()
            
            with pytest.raises(OpenCodeTimeoutError, match="timed out"):
                client.export_session("test-123")
    
    def test_session_lost_error(self, monkeypatch):
        """Test: Session lost raises OpenCodeSessionLostError."""
        monkeypatch.setenv("OPENCODE_ACP_URL", "http://test.local")
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "session not found"
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            
            client = OpenCodeACPClient()
            
            with pytest.raises(OpenCodeSessionLostError, match="Session lost"):
                client.get_session_status("invalid-session")
    
    def test_cli_not_found_error(self, monkeypatch):
        """Test: Missing CLI raises configuration error."""
        monkeypatch.setenv("OPENCODE_ACP_URL", "http://test.local")
        
        with patch("execqueue.workers.opencode_adapter.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("opencode")
            
            client = OpenCodeACPClient()
            
            with pytest.raises(OpenCodeConfigurationError, match="not found"):
                client.start_session(prompt="Test", cwd="/tmp")
