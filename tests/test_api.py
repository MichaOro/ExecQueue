from fastapi.testclient import TestClient

from execqueue.api.dependencies import get_request_context, resolve_request_context
from execqueue.main import app, create_app


def test_create_app_returns_fastapi_instance():
    created_app = create_app()
    assert created_app.title == "ExecQueue API"


def test_health_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["checks"]["api"]["status"] == "ok"
    assert payload["checks"]["api"]["component"] == "api"


def test_docs_endpoint_is_available():
    client = TestClient(app)

    response = client.get("/docs")

    assert response.status_code == 200


def test_openapi_endpoint_is_available():
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200


def test_openapi_contains_health_route():
    client = TestClient(app)

    response = client.get("/openapi.json")
    payload = response.json()

    assert "/health" in payload["paths"]


def test_openapi_describes_shared_ready_context():
    client = TestClient(app)

    response = client.get("/openapi.json")
    payload = response.json()
    info = payload["info"]

    assert info["title"] == "ExecQueue API"
    assert "multi-tenant" in info["description"]
    assert "single-tenant local" in info["summary"].lower()


def test_health_does_not_require_context_headers():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200


def test_health_endpoint_returns_aggregated_summary():
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert set(payload.keys()) == {"status", "checks"}
    assert "api" in payload["checks"]


def test_request_context_defaults_to_local_mode():
    context = resolve_request_context()

    assert context.mode == "single-tenant-local"
    assert context.tenant_id is None
    assert context.project_id is None


def test_request_context_accepts_shared_headers():
    context = resolve_request_context(
        tenant_id="tenant-alpha",
        project_id="project-42",
    )

    assert context.mode == "shared"
    assert context.tenant_id == "tenant-alpha"
    assert context.project_id == "project-42"


def test_fastapi_dependency_wrapper_maps_headers():
    context = get_request_context(
        x_tenant_id="tenant-alpha",
        x_project_id="project-42",
    )

    assert context.mode == "shared"
