import pytest
from sqlmodel import SQLModel

from execqueue.models.requirement import Requirement


class TestRequirementsAPI:
    """API tests for requirements endpoint."""

    def test_get_requirements_empty(self, api_client):
        """Test: GET /requirements returns empty list."""
        response = api_client.get("/requirements")

        assert response.status_code == 200
        assert response.json() == []

    def test_post_requirement(self, api_client):
        """Test: POST /requirements creates a requirement."""
        payload = {
            "title": "Test Requirement",
            "description": "Test description",
            "markdown_content": "# Test\n\nContent",
            "status": "backlog",
        }

        response = api_client.post("/requirements/", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Requirement"
        assert data["description"] == "Test description"
        assert "id" in data
        assert data["status"] == "backlog"

    def test_get_requirements_with_data(self, api_client, session_with_data):
        """Test: GET /requirements returns created requirements."""
        response = api_client.get("/requirements")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_post_requirement_minimal_payload(self, api_client):
        """Test: POST /requirements with minimal required fields."""
        payload = {
            "title": "Minimal",
            "description": "Minimal desc",
            "markdown_content": "Minimal content",
        }

        response = api_client.post("/requirements/", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal"
        assert data["status"] == "backlog"
