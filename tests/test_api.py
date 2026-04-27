from fastapi.testclient import TestClient

from execqueue.api.router import domain_router, system_router
from execqueue.main import app, create_app


def install_fake_healthchecks(
    monkeypatch,
    *,
    api_status: str = "OK",
    database_status: str = "OK",
    telegram_status: str = "OK",
    acp_status: str = "OK",
) -> None:
    from execqueue.health.models import HealthCheckResult

    monkeypatch.setattr(
        "execqueue.api.routes.health.get_api_healthcheck",
        lambda: HealthCheckResult(
            component="api",
            status=api_status,
            detail=(
                "API responded successfully."
                if api_status == "OK"
                else "API health check returned status 503."
            ),
        ),
    )
    monkeypatch.setattr(
        "execqueue.api.routes.health.get_database_healthcheck",
        lambda: HealthCheckResult(
            component="database",
            status=database_status,
            detail=(
                "Database connectivity check succeeded."
                if database_status == "OK"
                else "Database connectivity check failed."
            ),
        ),
    )
    monkeypatch.setattr(
        "execqueue.api.routes.health.get_telegram_bot_healthcheck",
        lambda: HealthCheckResult(
            component="telegram_bot",
            status=telegram_status,
            detail="Telegram bot health status available.",
        ),
    )
    monkeypatch.setattr(
        "execqueue.api.routes.health.get_acp_healthcheck",
        lambda: HealthCheckResult(
            component="acp",
            status=acp_status,
            detail="ACP health status available.",
        ),
    )


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
    assert "/restart" in system_paths
    assert "/restart" not in domain_paths


def test_system_restart_spawns_detached_process(monkeypatch, tmp_path):
    from execqueue.api.routes import system

    script_path = tmp_path / "global_restart.sh"
    script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    popen_calls: dict[str, object] = {}

    class FakeProcess:
        pid = 12345

    def fake_popen(*args, **kwargs):
        popen_calls["args"] = args
        popen_calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(system, "RESTART_SCRIPT", script_path)
    monkeypatch.setattr(system.subprocess, "Popen", fake_popen)

    client = TestClient(app)
    response = client.post("/restart")

    assert response.status_code == 200
    assert response.json()["pid"] == 12345
    assert popen_calls["args"] == ([str(script_path)],)
    assert popen_calls["kwargs"]["stdout"] is system.subprocess.DEVNULL
    assert popen_calls["kwargs"]["stderr"] is system.subprocess.DEVNULL
    assert popen_calls["kwargs"]["stdin"] is system.subprocess.DEVNULL
    assert popen_calls["kwargs"]["close_fds"] is True
    assert popen_calls["kwargs"]["start_new_session"] is True


class TestApiRestartEndpoint:
    """Tests for the API restart endpoint."""

    def test_api_restart_endpoint_exists(self, monkeypatch, tmp_path):
        from execqueue.api.routes import system

        script_path = tmp_path / "api_restart.sh"
        script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        class FakeProcess:
            pid = 12346

        def fake_popen(*args, **kwargs):
            return FakeProcess()

        monkeypatch.setattr(system, "API_RESTART_SCRIPT", script_path)
        monkeypatch.setattr(system.subprocess, "Popen", fake_popen)

        client = TestClient(app)
        response = client.post("/api/restart")

        assert response.status_code == 200
        assert response.json()["pid"] == 12346
        assert response.json()["status"] == "initiated"

    def test_api_restart_spawns_detached_process(self, monkeypatch, tmp_path):
        from execqueue.api.routes import system

        script_path = tmp_path / "api_restart.sh"
        script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        popen_calls: dict[str, object] = {}

        class FakeProcess:
            pid = 12346

        def fake_popen(*args, **kwargs):
            popen_calls["args"] = args
            popen_calls["kwargs"] = kwargs
            return FakeProcess()

        monkeypatch.setattr(system, "API_RESTART_SCRIPT", script_path)
        monkeypatch.setattr(system.subprocess, "Popen", fake_popen)

        client = TestClient(app)
        response = client.post("/api/restart")

        assert response.status_code == 200
        assert response.json()["pid"] == 12346
        assert popen_calls["args"] == ([str(script_path)],)
        assert popen_calls["kwargs"]["start_new_session"] is True

    def test_api_restart_script_not_found(self, monkeypatch):
        from execqueue.api.routes import system

        class FakePath:
            def exists(self):
                return False

        monkeypatch.setattr(system, "API_RESTART_SCRIPT", FakePath())

        client = TestClient(app)
        response = client.post("/api/restart")

        assert response.status_code == 500
        assert "not found" in response.json()["detail"].lower()

    def test_api_restart_permission_error(self, monkeypatch, tmp_path):
        from execqueue.api.routes import system

        script_path = tmp_path / "api_restart.sh"
        script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        def fake_popen(*args, **kwargs):
            raise PermissionError("Script not executable")

        monkeypatch.setattr(system, "API_RESTART_SCRIPT", script_path)
        monkeypatch.setattr(system.subprocess, "Popen", fake_popen)

        client = TestClient(app)
        response = client.post("/api/restart")

        assert response.status_code == 403
        assert "not executable" in response.json()["detail"].lower()


class TestTelegramBotRestartEndpoint:
    """Tests for the Telegram Bot restart endpoint."""

    def test_telegram_bot_restart_endpoint_exists(self, monkeypatch, tmp_path):
        from execqueue.api.routes import system

        script_path = tmp_path / "telegram_restart.sh"
        script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        class FakeProcess:
            pid = 12347

        def fake_popen(*args, **kwargs):
            return FakeProcess()

        monkeypatch.setattr(system, "TELEGRAM_RESTART_SCRIPT", script_path)
        monkeypatch.setattr(system.subprocess, "Popen", fake_popen)

        client = TestClient(app)
        response = client.post("/api/telegram_bot/restart")

        assert response.status_code == 200
        assert response.json()["pid"] == 12347
        assert response.json()["status"] == "initiated"

    def test_telegram_bot_restart_spawns_detached_process(self, monkeypatch, tmp_path):
        from execqueue.api.routes import system

        script_path = tmp_path / "telegram_restart.sh"
        script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        popen_calls: dict[str, object] = {}

        class FakeProcess:
            pid = 12347

        def fake_popen(*args, **kwargs):
            popen_calls["args"] = args
            popen_calls["kwargs"] = kwargs
            return FakeProcess()

        monkeypatch.setattr(system, "TELEGRAM_RESTART_SCRIPT", script_path)
        monkeypatch.setattr(system.subprocess, "Popen", fake_popen)

        client = TestClient(app)
        response = client.post("/api/telegram_bot/restart")

        assert response.status_code == 200
        assert popen_calls["kwargs"]["start_new_session"] is True

    def test_telegram_bot_restart_script_not_found(self, monkeypatch):
        from execqueue.api.routes import system

        class FakePath:
            def exists(self):
                return False

        monkeypatch.setattr(system, "TELEGRAM_RESTART_SCRIPT", FakePath())

        client = TestClient(app)
        response = client.post("/api/telegram_bot/restart")

        assert response.status_code == 500


class TestDatabaseConnectivityEndpoint:
    """Tests for the database-only connectivity endpoint."""

    def test_db_endpoint_exists(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, database_status="OK")
        client = TestClient(app)

        response = client.get("/db/health")

        assert response.status_code == 200

    def test_db_endpoint_returns_ok_when_connected(self, monkeypatch):
        from execqueue.health.models import HealthCheckResult

        monkeypatch.setattr(
            "execqueue.api.routes.health.get_database_healthcheck",
            lambda: HealthCheckResult(
                component="database",
                status="OK",
                detail="Database connectivity check succeeded.",
            ),
        )
        client = TestClient(app)

        response = client.get("/db/health")
        payload = response.json()

        assert payload["status"] == "OK"
        assert payload["component"] == "database"
        assert "succeeded" in payload["detail"].lower()

    def test_db_endpoint_returns_degraded_when_disconnected(self, monkeypatch):
        from execqueue.health.models import HealthCheckResult

        monkeypatch.setattr(
            "execqueue.api.routes.health.get_database_healthcheck",
            lambda: HealthCheckResult(
                component="database",
                status="DEGRADED",
                detail="Database connectivity check failed.",
            ),
        )
        client = TestClient(app)

        response = client.get("/db/health")
        payload = response.json()

        assert payload["status"] == "DEGRADED"
        assert payload["component"] == "database"
        assert "failed" in payload["detail"].lower()

    def test_db_endpoint_does_not_include_other_components(self, monkeypatch):
        from execqueue.health.models import HealthCheckResult

        monkeypatch.setattr(
            "execqueue.api.routes.health.get_database_healthcheck",
            lambda: HealthCheckResult(
                component="database",
                status="OK",
                detail="Database connectivity check succeeded.",
            ),
        )
        client = TestClient(app)

        response = client.get("/db/health")
        payload = response.json()

        # Should only have database, not api or checks dict
        assert payload["component"] == "database"
        assert "api" not in payload
        assert "checks" not in payload


class TestApiHealthEndpoint:
    """Tests for the explicit API health endpoint."""

    def test_api_health_endpoint_exists(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, api_status="OK")
        client = TestClient(app)

        response = client.get("/api/health")

        assert response.status_code == 200

    def test_api_health_returns_ok(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, api_status="OK")
        client = TestClient(app)

        response = client.get("/api/health")
        payload = response.json()

        assert payload["component"] == "api"
        assert payload["status"] == "OK"

    def test_api_health_returns_degraded_when_probe_fails(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, api_status="DEGRADED")
        client = TestClient(app)

        response = client.get("/api/health")
        payload = response.json()

        assert payload["component"] == "api"
        assert payload["status"] == "DEGRADED"


class TestHealthEndpointsInOpenAPI:
    """Tests for OpenAPI documentation coverage."""

    def test_api_health_endpoint_in_openapi(self):
        client = TestClient(app)

        response = client.get("/openapi.json")
        payload = response.json()

        assert "/api/health" in payload["paths"]

    def test_db_endpoint_in_openapi(self):
        client = TestClient(app)

        response = client.get("/openapi.json")
        payload = response.json()

        assert "/db/health" in payload["paths"]

    def test_health_endpoints_have_summaries(self):
        client = TestClient(app)

        response = client.get("/openapi.json")
        payload = response.json()

        assert payload["paths"]["/api/health"]["get"]["summary"] == "API component health check"
        assert payload["paths"]["/db/health"]["get"]["summary"] == "Database connectivity check"
