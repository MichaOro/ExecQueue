from fastapi.testclient import TestClient

from execqueue.api.router import domain_router, system_router
from execqueue.main import app, create_app


def install_fake_healthchecks(monkeypatch, database_status: str = "ok") -> None:
    from execqueue.health.models import HealthCheckResult

    def fake_healthchecks():
        return [
            lambda: HealthCheckResult(
                component="api",
                status="ok",
                detail="FastAPI application and Swagger/OpenAPI endpoints are available.",
            ),
            lambda: HealthCheckResult(
                component="database",
                status=database_status,
                detail=(
                    "Database connectivity check succeeded."
                    if database_status == "ok"
                    else "Database connectivity check failed."
                ),
            ),
        ]

    monkeypatch.setattr("execqueue.api.routes.health.get_registered_healthchecks", fake_healthchecks)


def test_create_app_returns_fastapi_instance():
    created_app = create_app()
    assert created_app.title == "ExecQueue API"


def test_health_endpoint_returns_ok(monkeypatch):
    install_fake_healthchecks(monkeypatch, database_status="ok")
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["checks"]["api"]["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "ok"
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


def test_health_does_not_require_context_headers(monkeypatch):
    install_fake_healthchecks(monkeypatch, database_status="ok")
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200


def test_health_route_stays_tenant_neutral_in_openapi():
    client = TestClient(app)

    response = client.get("/openapi.json")
    payload = response.json()
    health_operation = payload["paths"]["/health"]["get"]

    assert "parameters" not in health_operation


def test_health_endpoint_returns_aggregated_summary(monkeypatch):
    install_fake_healthchecks(monkeypatch, database_status="ok")
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert set(payload.keys()) == {"status", "checks"}
    assert "api" in payload["checks"]
    assert "database" in payload["checks"]


def test_health_endpoint_reports_degraded_when_database_check_fails(monkeypatch):
    install_fake_healthchecks(monkeypatch, database_status="degraded")
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"]["status"] == "degraded"
    assert "secret" not in payload["checks"]["database"]["detail"].lower()


def test_router_structure_separates_system_and_domain_areas():
    system_paths = {route.path for route in system_router.routes}
    domain_paths = {route.path for route in domain_router.routes}

    assert "/health" in system_paths
    assert domain_paths == set()
