from fastapi.testclient import TestClient

from execqueue.api.router import domain_router, system_router
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
    assert "X-Tenant-ID" in info["description"]
    assert "tenant-neutral" in info["summary"].lower()


def test_health_does_not_require_context_headers():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200


def test_health_route_stays_tenant_neutral_in_openapi():
    client = TestClient(app)

    response = client.get("/openapi.json")
    payload = response.json()
    health_operation = payload["paths"]["/health"]["get"]

    assert "parameters" not in health_operation


def test_health_endpoint_returns_aggregated_summary():
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert set(payload.keys()) == {"status", "checks"}
    assert "api" in payload["checks"]


def test_router_structure_separates_system_and_domain_areas():
    system_paths = {route.path for route in system_router.routes}
    domain_paths = {route.path for route in domain_router.routes}

    assert "/health" in system_paths
    assert domain_paths == set()
