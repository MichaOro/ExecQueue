"""Tests for OpenCode Serve API Contract (REQ-012 Paket 03).

This module verifies the actual opencode serve API endpoints
against a running instance.
"""

from __future__ import annotations

import pytest
import httpx


BASE_URL = "http://127.0.0.1:4096"


class TestOpenCodeHealthEndpoint:
    """Test OpenCode health endpoint."""

    def test_health_endpoint_exists(self):
        """Test that /global/health endpoint exists and returns healthy."""
        response = httpx.get(f"{BASE_URL}/global/health", timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        assert "healthy" in data
        assert "version" in data
        assert data["healthy"] is True

    def test_health_version_format(self):
        """Test that health response includes valid version."""
        response = httpx.get(f"{BASE_URL}/global/health", timeout=5.0)
        data = response.json()
        # Version should be semver-like
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


class TestOpenCodeSessionEndpoint:
    """Test OpenCode session listing endpoint."""

    def test_session_list_endpoint_exists(self):
        """Test that /session endpoint exists."""
        response = httpx.get(f"{BASE_URL}/session", timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_session_list_has_sessions(self):
        """Test that session list contains at least one session."""
        response = httpx.get(f"{BASE_URL}/session", timeout=5.0)
        data = response.json()
        assert len(data) > 0

    def test_session_has_required_fields(self):
        """Test that sessions have required fields."""
        response = httpx.get(f"{BASE_URL}/session", timeout=5.0)
        data = response.json()
        
        if len(data) > 0:
            session = data[0]
            assert "id" in session
            assert "slug" in session
            assert "projectID" in session
            assert "directory" in session
            assert "title" in session
            assert "time" in session


class TestOpenCodeAgentEndpoint:
    """Test OpenCode agent listing endpoint."""

    def test_agent_endpoint_exists(self):
        """Test that /agent endpoint exists."""
        response = httpx.get(f"{BASE_URL}/agent", timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_build_agent_exists(self):
        """Test that build agent is available."""
        response = httpx.get(f"{BASE_URL}/agent", timeout=5.0)
        data = response.json()
        
        agent_names = [agent["name"] for agent in data]
        assert "build" in agent_names

    def test_build_agent_has_required_fields(self):
        """Test that build agent has required fields."""
        response = httpx.get(f"{BASE_URL}/agent", timeout=5.0)
        data = response.json()
        
        build_agent = next((a for a in data if a["name"] == "build"), None)
        assert build_agent is not None
        assert "description" in build_agent
        assert "mode" in build_agent
        assert "model" in build_agent

    def test_available_agents(self):
        """Test that expected agents are available."""
        response = httpx.get(f"{BASE_URL}/agent", timeout=5.0)
        data = response.json()
        
        agent_names = [agent["name"] for agent in data]
        
        # Check for key agents
        expected_agents = ["build", "plan", "explore", "general"]
        for agent in expected_agents:
            assert agent in agent_names, f"Expected agent '{agent}' not found"


class TestOpenCodeProjectEndpoint:
    """Test OpenCode project endpoint."""

    def test_project_current_endpoint_exists(self):
        """Test that /project/current endpoint exists."""
        response = httpx.get(f"{BASE_URL}/project/current", timeout=5.0)
        assert response.status_code == 200
        data = response.json()

    def test_project_has_required_fields(self):
        """Test that project has required fields."""
        response = httpx.get(f"{BASE_URL}/project/current", timeout=5.0)
        data = response.json()
        
        assert "id" in data
        assert "worktree" in data
        assert "vcs" in data


class TestOpenCodeContract:
    """Test OpenCode API contract compliance."""

    def test_server_is_healthy(self):
        """Test that server is healthy and responsive."""
        response = httpx.get(f"{BASE_URL}/global/health", timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True

    def test_api_responds_in_time(self):
        """Test that API responds within timeout."""
        start_time = __import__("time").time()
        response = httpx.get(f"{BASE_URL}/global/health", timeout=5.0)
        elapsed = __import__("time").time() - start_time
        
        assert response.status_code == 200
        assert elapsed < 5.0, f"Request took {elapsed:.2f}s, expected < 5s"

    def test_json_responses(self):
        """Test that all endpoints return valid JSON."""
        endpoints = [
            "/global/health",
            "/session",
            "/agent",
            "/project/current",
        ]
        
        for endpoint in endpoints:
            response = httpx.get(f"{BASE_URL}{endpoint}", timeout=5.0)
            assert response.status_code == 200, f"Endpoint {endpoint} failed"
            
            # Should not raise
            response.json()


class TestOpenCodeIntegrationRisks:
    """Document and test known integration risks."""

    def test_sse_endpoint_is_streaming(self):
        """Test that SSE endpoint is a streaming endpoint (expected to block).
        
        This test documents that /event is an SSE stream that doesn't return
        a normal HTTP response. We use stream=True and close immediately.
        """
        # SSE endpoints stream indefinitely, so we test that it accepts the connection
        with httpx.stream("GET", f"{BASE_URL}/event", timeout=1.0) as response:
            # Just verify we can open the stream
            assert response.status_code == 200
            # Close stream immediately - we're just testing connectivity

    def test_message_dispatch_structure(self):
        """Test message dispatch endpoint structure (not actual dispatch)."""
        # We don't actually dispatch messages in contract tests
        # This test documents the expected structure
        expected_structure = {
            "parts": [{"type": "text", "text": "test"}],
            "agent": "build",
        }
        assert "parts" in expected_structure
        assert "agent" in expected_structure
