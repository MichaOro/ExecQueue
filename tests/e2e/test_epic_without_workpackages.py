import pytest
from unittest.mock import patch
from sqlmodel import select

from execqueue.models.requirement import Requirement
from tests.e2e.conftest import mock_opencode_done


class TestEpicWithoutWorkPackages:
    """E2E tests for Epic/Requirement without WorkPackages."""

    def test_full_flow_epic_without_workpackages(self, e2e_client):
        """
        Use Case: Complete flow for Epic without WorkPackages.
        
        Steps:
        1. Create Requirement
        2. Enqueue Requirement (creates 1 Task)
        3. Run Next Task (mocked success)
        4. Validate final state
        """
        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_done(),
        ):
            payload = {
                "title": "Epic Without WPs",
                "description": "Description",
                "markdown_content": "# Epic\n\nContent",
            }

            response = e2e_client.post("/requirements", json=payload)
            assert response.status_code == 201
            req = response.json()
            requirement_id = req["id"]

            response = e2e_client.post(
                "/queue/enqueue-requirement", json={"requirement_id": requirement_id}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["created_task_count"] == 1

            response = e2e_client.post("/runner/run-next")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "done"

            response = e2e_client.get(f"/requirements/")
            requirements = response.json()
            epic = next(r for r in requirements if r["id"] == requirement_id)
            assert epic["status"] == "done"

    def test_multiple_epics_parallel_enqueue(self, e2e_client):
        """
        Use Case: Multiple Epics enqueued in parallel.
        
        Steps:
        1. Create 3 Requirements
        2. Enqueue all 3 (creates 3 Tasks)
        3. Process all Tasks (mocked success)
        4. Validate all Requirements are done
        """
        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_done(),
        ):
            for i in range(3):
                response = e2e_client.post(
                    "/requirements",
                    json={
                        "title": f"Epic {i}",
                        "description": f"Description {i}",
                        "markdown_content": f"# Epic {i}",
                    },
                )
                assert response.status_code == 201

            response = e2e_client.get("/requirements/")
            requirements = response.json()

            for req in requirements:
                response = e2e_client.post(
                    "/queue/enqueue-requirement", json={"requirement_id": req["id"]}
                )
                assert response.status_code == 200

            for _ in range(3):
                response = e2e_client.post("/runner/run-next")
                assert response.status_code == 200

            response = e2e_client.get("/requirements/")
            requirements = response.json()
            for req in requirements:
                assert req["status"] == "done"
