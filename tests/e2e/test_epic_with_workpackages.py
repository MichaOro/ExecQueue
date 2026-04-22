import pytest
from unittest.mock import patch
from sqlmodel import select

from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task
from tests.e2e.conftest import mock_opencode_done, mock_opencode_not_done


class TestEpicWithWorkPackages:
    """E2E tests for Epic/Requirement with WorkPackages."""

    def test_full_flow_epic_with_two_workpackages(self, e2e_client):
        """
        Use Case: Complete flow for Epic with 2 WorkPackages.
        
        Steps:
        1. Create Requirement
        2. Create 2 WorkPackages
        3. Enqueue Requirement (creates 2 Tasks)
        4. Process both Tasks (mocked success)
        5. Validate all entities are done
        """
        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_done(),
        ):
            response = e2e_client.post(
                "/requirements",
                json={
                    "title": "Epic With WPs",
                    "description": "Description",
                    "markdown_content": "# Epic\n\nContent",
                },
            )
            assert response.status_code == 201
            req_id = response.json()["id"]

            for i in range(2):
                response = e2e_client.post(
                    "/work-packages",
                    json={
                        "requirement_id": req_id,
                        "title": f"WP {i}",
                        "description": f"Description {i}",
                        "execution_order": i + 1,
                    },
                )
                assert response.status_code == 201

            response = e2e_client.post(
                "/queue/enqueue-requirement", json={"requirement_id": req_id}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["created_task_count"] == 2

            for i in range(2):
                response = e2e_client.post("/runner/run-next")
                assert response.status_code == 200

            response = e2e_client.get("/requirements/")
            epic = next(r for r in response.json() if r["id"] == req_id)
            assert epic["status"] == "done"

            response = e2e_client.get("/work-packages/")
            wps = [wp for wp in response.json() if wp["requirement_id"] == req_id]
            for wp in wps:
                assert wp["status"] == "done"

    def test_execution_order_enforcement(self, e2e_client):
        """
        Use Case: Execution order is respected.
        
        Steps:
        1. Create Requirement + 3 WorkPackages (order 1, 2, 3)
        2. Enqueue Requirement
        3. Process Tasks sequentially
        4. Validate execution order
        """
        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_done(),
        ):
            response = e2e_client.post(
                "/requirements",
                json={
                    "title": "Epic Order Test",
                    "description": "Description",
                    "markdown_content": "# Epic",
                },
            )
            assert response.status_code == 201
            req_id = response.json()["id"]

            for order in [1, 2, 3]:
                response = e2e_client.post(
                    "/work-packages",
                    json={
                        "requirement_id": req_id,
                        "title": f"WP Order {order}",
                        "description": f"Order {order}",
                        "execution_order": order,
                    },
                )
                assert response.status_code == 201

            response = e2e_client.post(
                "/queue/enqueue-requirement", json={"requirement_id": req_id}
            )
            assert response.status_code == 200

            execution_order = []
            for _ in range(3):
                response = e2e_client.post("/runner/run-next")
                assert response.status_code == 200
                data = response.json()
                execution_order.append(data["source_id"])

            response = e2e_client.get("/work-packages/")
            wps = {wp["id"]: wp["execution_order"] for wp in response.json()}

            processed_orders = [wps[wp_id] for wp_id in execution_order]
            assert processed_orders == [1, 2, 3]

    def test_partial_failure_with_retry(self, e2e_client):
        """
        Use Case: Partial failure with retry logic.
        
        Steps:
        1. Create Requirement + 2 WorkPackages
        2. Mock WP1 to fail twice then succeed, WP2 succeeds immediately
        3. Process Tasks
        4. Validate final state
        """
        call_count = {"wp1": 0, "wp2": 0}

        def flaky_opencode(prompt: str, verification_prompt: str = None):
            if "WP 0" in prompt or "WP 1" in prompt:
                call_count["wp1"] += 1
                if call_count["wp1"] < 3:
                    return mock_opencode_not_done()
                return mock_opencode_done()
            else:
                call_count["wp2"] += 1
                return mock_opencode_done()

        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            side_effect=flaky_opencode,
        ):
            response = e2e_client.post(
                "/requirements",
                json={
                    "title": "Epic Partial Failure",
                    "description": "Description",
                    "markdown_content": "# Epic",
                },
            )
            assert response.status_code == 201
            req_id = response.json()["id"]

            for i in range(2):
                response = e2e_client.post(
                    "/work-packages",
                    json={
                        "requirement_id": req_id,
                        "title": f"WP {i}",
                        "description": f"Description {i}",
                        "execution_order": i + 1,
                    },
                )
                assert response.status_code == 201

            response = e2e_client.post(
                "/queue/enqueue-requirement", json={"requirement_id": req_id}
            )
            assert response.status_code == 200

            for _ in range(4):
                response = e2e_client.post("/runner/run-next")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "done":
                        continue

            response = e2e_client.get("/work-packages/")
            wps = [wp for wp in response.json() if wp["requirement_id"] == req_id]
            for wp in wps:
                assert wp["status"] == "done"

    def test_retry_limit_reached(self, e2e_client):
        """
        Use Case: Task fails after exhausting max_retries.
        
        Steps:
        1. Create Requirement + 1 WorkPackage with low max_retries
        2. Mock always failure
        3. Process Task multiple times
        4. Validate Task is marked as failed
        """
        with patch(
            "execqueue.scheduler.runner.execute_with_opencode",
            return_value=mock_opencode_not_done(),
        ):
            response = e2e_client.post(
                "/requirements",
                json={
                    "title": "Epic Retry Limit",
                    "description": "Description",
                    "markdown_content": "# Epic",
                },
            )
            assert response.status_code == 201
            req_id = response.json()["id"]

            response = e2e_client.post(
                "/work-packages",
                json={
                    "requirement_id": req_id,
                    "title": "WP Retry Limit",
                    "description": "Description",
                    "execution_order": 1,
                },
            )
            assert response.status_code == 201
            wp_id = response.json()["id"]

            response = e2e_client.post(
                "/tasks",
                json={
                    "source_type": "work_package",
                    "source_id": wp_id,
                    "title": "Task Retry Limit",
                    "prompt": "Prompt",
                    "execution_order": 1,
                    "max_retries": 2,
                },
            )
            assert response.status_code == 201
            task_id = response.json()["id"]

            for _ in range(3):
                response = e2e_client.post("/runner/run-next")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "failed":
                        break

            response = e2e_client.get("/tasks/")
            task = next(t for t in response.json() if t["id"] == task_id)
            assert task["status"] == "failed"
            assert task["retry_count"] == 2
