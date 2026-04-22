import pytest
from sqlmodel import select

from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage


class TestWorkPackagesAPI:
    """API tests for work-packages endpoint."""

    def test_get_work_packages_empty(self, api_client):
        """Test: GET /work-packages returns empty list."""
        response = api_client.get("/work-packages")

        assert response.status_code == 200
        assert response.json() == []

    def test_post_work_package(self, api_client, session_with_data):
        """Test: POST /work-packages creates a work package."""
        req_id = session_with_data.exec(select(Requirement.id).limit(1)).first()

        payload = {
            "requirement_id": req_id,
            "title": "New Work Package",
            "description": "New WP description",
            "execution_order": 2,
            "status": "backlog",
        }

        response = api_client.post("/work-packages", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Work Package"
        assert data["requirement_id"] == req_id
        assert "id" in data

    def test_get_work_packages_with_data(self, api_client, session_with_data):
        """Test: GET /work-packages returns created work packages."""
        response = api_client.get("/work-packages")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_post_work_package_minimal_payload(self, api_client, session_with_data):
        """Test: POST /work-packages with minimal required fields."""
        req_id = session_with_data.exec(select(Requirement.id).limit(1)).first()

        payload = {
            "requirement_id": req_id,
            "title": "Minimal WP",
            "description": "Minimal description",
        }

        response = api_client.post("/work-packages", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal WP"
        assert data["execution_order"] == 0
        assert data["status"] == "backlog"

    def test_post_work_package_with_verification_prompt(self, api_client, session_with_data):
        """Test: POST /work-packages with optional verification_prompt."""
        req_id = session_with_data.exec(select(Requirement.id).limit(1)).first()

        payload = {
            "requirement_id": req_id,
            "title": "WP with verification",
            "description": "Description",
            "implementation_prompt": "Implement this",
            "verification_prompt": "Verify this",
            "execution_order": 1,
        }

        response = api_client.post("/work-packages", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["implementation_prompt"] == "Implement this"
        assert data["verification_prompt"] == "Verify this"
