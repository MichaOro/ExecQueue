from fastapi.testclient import TestClient

from execqueue.api.router import domain_router, system_router
from execqueue.main import app, create_app


def install_fake_healthchecks(monkeypatch, database_status: str = "OK") -> None:
    from execqueue.health.models import HealthCheckResult

    def fake_healthchecks():
        return [
            lambda: HealthCheckResult(
                component="api",
                status="OK",
                detail="FastAPI application and Swagger/OpenAPI endpoints are available.",
            ),
            lambda: HealthCheckResult(
                component="database",
                status=database_status,
                detail=(
                    "Database connectivity check succeeded."
                    if database_status == "OK"
                    else "Database connectivity check failed."
                ),
            ),
        ]

    monkeypatch.setattr("execqueue.api.routes.health.get_registered_healthchecks", fake_healthchecks)


def test_create_app_returns_fastapi_instance():
    created_app = create_app()
    assert created_app.title == "ExecQueue API"


def test_health_endpoint_returns_ok(monkeypatch):
    install_fake_healthchecks(monkeypatch, database_status="OK")
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "OK"
    assert payload["checks"]["api"]["status"] == "OK"
    assert payload["checks"]["database"]["status"] == "OK"
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
    install_fake_healthchecks(monkeypatch, database_status="OK")
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
    install_fake_healthchecks(monkeypatch, database_status="OK")
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert set(payload.keys()) == {"status", "checks"}
    assert "api" in payload["checks"]
    assert "database" in payload["checks"]


def test_health_endpoint_reports_degraded_when_database_check_fails(monkeypatch):
    install_fake_healthchecks(monkeypatch, database_status="DEGRADED")
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "DEGRADED"
    assert payload["checks"]["database"]["status"] == "DEGRADED"
    assert "secret" not in payload["checks"]["database"]["detail"].lower()


def test_router_structure_separates_system_and_domain_areas():
    system_paths = {route.path for route in system_router.routes}
    domain_paths = {route.path for route in domain_router.routes}

    assert "/health" in system_paths
    # Domain router now has system restart endpoint
    assert "/api/system/restart" in domain_paths


def test_system_restart_spawns_detached_process(monkeypatch, tmp_path):
    from execqueue.api.routes import domain

    script_path = tmp_path / "global_restart.sh"
    script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    popen_calls: dict[str, object] = {}

    class FakeProcess:
        pid = 12345

    def fake_popen(*args, **kwargs):
        popen_calls["args"] = args
        popen_calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(domain, "RESTART_SCRIPT", script_path)
    monkeypatch.setattr(domain.subprocess, "Popen", fake_popen)

    client = TestClient(app)
    response = client.post("/api/system/restart")

    assert response.status_code == 200
    assert response.json()["pid"] == 12345
    assert popen_calls["args"] == ([str(script_path)],)
    assert popen_calls["kwargs"]["stdout"] is domain.subprocess.DEVNULL
    assert popen_calls["kwargs"]["stderr"] is domain.subprocess.DEVNULL
    assert popen_calls["kwargs"]["stdin"] is domain.subprocess.DEVNULL
    assert popen_calls["kwargs"]["close_fds"] is True
    assert popen_calls["kwargs"]["start_new_session"] is True


class TestLivenessEndpoint:
    """Tests for the liveness probe endpoint."""

    def test_liveness_endpoint_exists(self):
        client = TestClient(app)

        response = client.get("/health/live")

        assert response.status_code == 200

    def test_liveness_returns_ok_status(self):
        client = TestClient(app)

        response = client.get("/health/live")
        payload = response.json()

        assert payload["status"] == "OK"
        assert payload["component"] == "api"
        assert payload["detail"] == "API is alive and responding."

    def test_liveness_does_not_check_database(self):
        """Liveness should always return OK regardless of DB state."""
        client = TestClient(app)

        response = client.get("/health/live")
        payload = response.json()

        # Liveness should not include database check
        assert "database" not in payload
        assert payload["component"] == "api"


class TestReadinessEndpoint:
    """Tests for the readiness probe endpoint."""

    def test_readiness_endpoint_exists(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, database_status="OK")
        client = TestClient(app)

        response = client.get("/health/ready")

        assert response.status_code == 200

    def test_readiness_returns_ok_when_db_ok(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, database_status="OK")
        client = TestClient(app)

        response = client.get("/health/ready")
        payload = response.json()

        assert payload["status"] == "OK"
        assert payload["checks"]["api"]["status"] == "OK"
        assert payload["checks"]["database"]["status"] == "OK"

    def test_readiness_returns_degraded_when_db_degraded(self, monkeypatch):
        from execqueue.health.models import HealthCheckResult

        def fake_readiness_checks():
            return [
                lambda: HealthCheckResult(
                    component="api",
                    status="OK",
                    detail="API is ready.",
                ),
                lambda: HealthCheckResult(
                    component="database",
                    status="DEGRADED",
                    detail="Database connectivity check failed.",
                ),
            ]

        monkeypatch.setattr("execqueue.api.routes.health.get_registered_healthchecks", fake_readiness_checks)
        monkeypatch.setattr(
            "execqueue.db.health.get_database_healthcheck",
            lambda: HealthCheckResult(
                component="database",
                status="DEGRADED",
                detail="Database connectivity check failed.",
            ),
        )
        client = TestClient(app)

        response = client.get("/health/ready")
        payload = response.json()

        assert payload["status"] == "DEGRADED"
        assert payload["checks"]["api"]["status"] == "OK"
        assert payload["checks"]["database"]["status"] == "DEGRADED"

    def test_readiness_includes_api_and_database_checks(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, database_status="OK")
        client = TestClient(app)

        response = client.get("/health/ready")
        payload = response.json()

        assert set(payload["checks"].keys()) == {"api", "database"}


class TestDatabaseConnectivityEndpoint:
    """Tests for the database-only connectivity endpoint."""

    def test_db_endpoint_exists(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, database_status="OK")
        client = TestClient(app)

        response = client.get("/health/db")

        assert response.status_code == 200

    def test_db_endpoint_returns_ok_when_connected(self, monkeypatch):
        from execqueue.health.models import HealthCheckResult

        monkeypatch.setattr(
            "execqueue.db.health.get_database_healthcheck",
            lambda: HealthCheckResult(
                component="database",
                status="OK",
                detail="Database connectivity check succeeded.",
            ),
        )
        client = TestClient(app)

        response = client.get("/health/db")
        payload = response.json()

        assert payload["status"] == "OK"
        assert payload["component"] == "database"
        assert "succeeded" in payload["detail"].lower()

    def test_db_endpoint_returns_degraded_when_disconnected(self, monkeypatch):
        from execqueue.health.models import HealthCheckResult

        monkeypatch.setattr(
            "execqueue.db.health.get_database_healthcheck",
            lambda: HealthCheckResult(
                component="database",
                status="DEGRADED",
                detail="Database connectivity check failed.",
            ),
        )
        client = TestClient(app)

        response = client.get("/health/db")
        payload = response.json()

        assert payload["status"] == "DEGRADED"
        assert payload["component"] == "database"
        assert "failed" in payload["detail"].lower()

    def test_db_endpoint_does_not_include_other_components(self, monkeypatch):
        from execqueue.health.models import HealthCheckResult

        monkeypatch.setattr(
            "execqueue.db.health.get_database_healthcheck",
            lambda: HealthCheckResult(
                component="database",
                status="OK",
                detail="Database connectivity check succeeded.",
            ),
        )
        client = TestClient(app)

        response = client.get("/health/db")
        payload = response.json()

        # Should only have database, not api or checks dict
        assert payload["component"] == "database"
        assert "api" not in payload
        assert "checks" not in payload


class TestHealthEndpointsInOpenAPI:
    """Tests for OpenAPI documentation coverage."""

    def test_liveness_endpoint_in_openapi(self):
        client = TestClient(app)

        response = client.get("/openapi.json")
        payload = response.json()

        assert "/health/live" in payload["paths"]

    def test_readiness_endpoint_in_openapi(self):
        client = TestClient(app)

        response = client.get("/openapi.json")
        payload = response.json()

        assert "/health/ready" in payload["paths"]

    def test_db_endpoint_in_openapi(self):
        client = TestClient(app)

        response = client.get("/openapi.json")
        payload = response.json()

        assert "/health/db" in payload["paths"]

    def test_health_endpoints_have_summaries(self):
        client = TestClient(app)

        response = client.get("/openapi.json")
        payload = response.json()

        assert payload["paths"]["/health/live"]["get"]["summary"] == "Liveness probe"
        assert payload["paths"]["/health/ready"]["get"]["summary"] == "Readiness probe"
        assert payload["paths"]["/health/db"]["get"]["summary"] == "Database connectivity check"
