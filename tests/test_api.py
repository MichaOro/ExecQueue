from fastapi.testclient import TestClient

from execqueue.api.router import domain_router, system_router
from execqueue.main import app, create_app


def install_system_admin_token(monkeypatch, token: str = "test-admin-token") -> dict[str, str]:
    from execqueue.settings import Settings

    monkeypatch.setattr(
        "execqueue.api.dependencies.get_settings",
        lambda: Settings(system_admin_token=token),
    )
    return {"X-Admin-Token": token}


def install_telegram_admin_user(monkeypatch, telegram_id: int = 123456789) -> dict[str, str]:
    """Set up a mock Telegram admin user in the database for testing."""
    from unittest.mock import MagicMock
    
    # Create a mock admin user
    mock_user = MagicMock()
    mock_user.telegram_id = telegram_id
    mock_user.role = "admin"
    mock_user.is_active = True
    
    # Mock the database query
    def mock_execute(query):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        return mock_result
    
    # Create a mock session
    mock_session = MagicMock()
    mock_session.execute = mock_execute
    
    monkeypatch.setattr(
        "execqueue.api.dependencies.get_session",
        lambda: iter([mock_session]),
    )
    return {"X-Telegram-User-ID": str(telegram_id)}


def install_fake_healthchecks(
    monkeypatch,
    *,
    api_status: str = "OK",
    database_status: str = "OK",
    telegram_status: str = "OK",
    opencode_status: str = "OK",
    opencode_state: str = "reachable",
) -> None:
    from execqueue.health.models import HealthCheckResult

    monkeypatch.setattr(
        "execqueue.api.routes.health.get_api_healthcheck",
        lambda: HealthCheckResult(component="api", status=api_status, detail="API health."),
    )
    monkeypatch.setattr(
        "execqueue.api.routes.health.get_database_healthcheck",
        lambda: HealthCheckResult(
            component="database", status=database_status, detail="Database health."
        ),
    )
    monkeypatch.setattr(
        "execqueue.api.routes.health.get_telegram_bot_healthcheck",
        lambda: HealthCheckResult(
            component="telegram_bot", status=telegram_status, detail="Telegram health."
        ),
    )
    monkeypatch.setattr(
        "execqueue.api.routes.health.get_opencode_healthcheck",
        lambda: HealthCheckResult(
            component="opencode",
            status=opencode_status,
            detail="OpenCode health.",
            state=opencode_state,
        ),
    )


def test_create_app_returns_fastapi_instance():
    created_app = create_app()
    assert created_app.title == "ExecQueue API"


def test_health_endpoint_returns_ok(monkeypatch):
    install_fake_healthchecks(monkeypatch)
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "OK"
    assert payload["checks"]["opencode"]["component"] == "opencode"


def test_docs_endpoint_is_available():
    assert TestClient(app).get("/docs").status_code == 200


def test_openapi_endpoint_is_available():
    assert TestClient(app).get("/openapi.json").status_code == 200


def test_openapi_contains_health_route():
    payload = TestClient(app).get("/openapi.json").json()
    assert "/health" in payload["paths"]


def test_openapi_describes_shared_ready_context():
    payload = TestClient(app).get("/openapi.json").json()
    assert payload["info"]["title"] == "ExecQueue API"
    assert "X-Tenant-ID" in payload["info"]["description"]
    assert "tenant-neutral" in payload["info"]["summary"].lower()


def test_health_route_stays_tenant_neutral_in_openapi():
    payload = TestClient(app).get("/openapi.json").json()
    assert "parameters" not in payload["paths"]["/health"]["get"]


def test_health_endpoint_core_ok_when_opencode_unreachable(monkeypatch):
    """OpenCode being unreachable should not degrade core system status."""
    install_fake_healthchecks(
        monkeypatch,
        opencode_status="DEGRADED",
        opencode_state="unreachable",
    )
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    # Core status should be OK because OpenCode is optional
    assert payload["status"] == "OK"
    assert payload["checks"]["opencode"]["state"] == "unreachable"


def test_health_endpoint_core_ok_when_opencode_disabled(monkeypatch):
    """OpenCode being disabled should not degrade core system status."""
    install_fake_healthchecks(
        monkeypatch,
        opencode_status="DEGRADED",
        opencode_state="disabled",
    )
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "OK"
    assert payload["checks"]["opencode"]["state"] == "disabled"


def test_health_endpoint_core_ok_when_opencode_timeout(monkeypatch):
    """OpenCode timeout should not degrade core system status."""
    install_fake_healthchecks(
        monkeypatch,
        opencode_status="DEGRADED",
        opencode_state="timeout",
    )
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "OK"
    assert payload["checks"]["opencode"]["state"] == "timeout"


def test_health_endpoint_core_ok_when_opencode_unexpected_response(monkeypatch):
    """OpenCode unexpected response should not degrade core system status."""
    install_fake_healthchecks(
        monkeypatch,
        opencode_status="DEGRADED",
        opencode_state="unexpected_response",
    )
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "OK"
    assert payload["checks"]["opencode"]["state"] == "unexpected_response"


def test_health_endpoint_core_ok_when_opencode_available(monkeypatch):
    """OpenCode available should show OK for both core and OpenCode."""
    install_fake_healthchecks(
        monkeypatch,
        opencode_status="OK",
        opencode_state="available",
    )
    client = TestClient(app)

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "OK"
    assert payload["checks"]["opencode"]["state"] == "available"


def test_router_structure_separates_system_and_domain_areas():
    system_paths = {route.path for route in system_router.routes}
    domain_paths = {route.path for route in domain_router.routes}

    assert "/health" in system_paths
    assert "/restart" in system_paths
    assert "/restart" not in domain_paths
    assert "/api/system/acp/restart" not in system_paths


def test_system_restart_spawns_detached_process(monkeypatch, tmp_path):
    from execqueue.api.routes import system

    headers = install_system_admin_token(monkeypatch)
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

    response = TestClient(app).post("/restart", headers=headers)

    assert response.status_code == 200
    assert response.json()["pid"] == 12345
    assert popen_calls["kwargs"]["start_new_session"] is True


class TestApiRestartEndpoint:
    def test_api_restart_endpoint_exists(self, monkeypatch, tmp_path):
        from execqueue.api.routes import system

        headers = install_system_admin_token(monkeypatch)
        script_path = tmp_path / "api_restart.sh"
        script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        class FakeProcess:
            pid = 12346

        monkeypatch.setattr(system, "API_RESTART_SCRIPT", script_path)
        monkeypatch.setattr(system.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

        response = TestClient(app).post("/api/restart", headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "initiated"

    def test_api_restart_script_not_found(self, monkeypatch):
        from execqueue.api.routes import system

        headers = install_system_admin_token(monkeypatch)

        class FakePath:
            def exists(self):
                return False

        monkeypatch.setattr(system, "API_RESTART_SCRIPT", FakePath())
        response = TestClient(app).post("/api/restart", headers=headers)

        assert response.status_code == 500
        assert response.json()["detail"] == "Restart script not found."


class TestTelegramBotRestartEndpoint:
    def test_telegram_bot_restart_endpoint_exists(self, monkeypatch, tmp_path):
        from execqueue.api.routes import system

        headers = install_system_admin_token(monkeypatch)
        script_path = tmp_path / "telegram_restart.sh"
        script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        class FakeProcess:
            pid = 12347

        monkeypatch.setattr(system, "TELEGRAM_RESTART_SCRIPT", script_path)
        monkeypatch.setattr(system.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

        response = TestClient(app).post("/api/telegram_bot/restart", headers=headers)
        assert response.status_code == 200


class TestSystemRestartAuthorization:
    def test_restart_requires_admin_token(self):
        assert TestClient(app).post("/restart").status_code in {403, 503}

    def test_restart_rejects_wrong_admin_token(self, monkeypatch):
        install_system_admin_token(monkeypatch, token="expected-token")
        response = TestClient(app).post("/restart", headers={"X-Admin-Token": "wrong-token"})

        assert response.status_code == 403

    def test_restart_accepts_telegram_admin_user(self, monkeypatch, tmp_path):
        """Telegram admin users should be able to restart without token."""
        from execqueue.api.routes import system
        from unittest.mock import MagicMock, patch
        
        # Create a mock admin user
        mock_user = MagicMock()
        mock_user.telegram_id = 123456789
        mock_user.role = "admin"
        mock_user.is_active = True
        
        # Mock the session's execute method
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_user
        mock_session.close = MagicMock()
        
        script_path = tmp_path / "global_restart.sh"
        script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        class FakeProcess:
            pid = 12348

        monkeypatch.setattr(system, "RESTART_SCRIPT", script_path)
        monkeypatch.setattr(system.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
        
        # Patch create_session where it's used
        with patch("execqueue.api.dependencies.create_session", return_value=mock_session):
            response = TestClient(app).post("/restart", headers={"X-Telegram-User-ID": "123456789"})

        assert response.status_code == 200
        assert response.json()["pid"] == 12348

    def test_restart_rejects_non_admin_telegram_user(self, monkeypatch):
        """Non-admin Telegram users should be rejected."""
        from unittest.mock import MagicMock, patch
        
        # Create a mock non-admin user
        mock_user = MagicMock()
        mock_user.telegram_id = 987654321
        mock_user.role = "user"
        mock_user.is_active = True
        
        # Mock the session's execute method
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_user
        mock_session.close = MagicMock()
        
        # Patch create_session where it's used
        with patch("execqueue.api.dependencies.create_session", return_value=mock_session):
            response = TestClient(app).post("/restart", headers={"X-Telegram-User-ID": "987654321"})

        assert response.status_code == 403
        assert "Admin role required" in response.json()["detail"]

    def test_restart_rejects_inactive_telegram_user(self, monkeypatch):
        """Inactive Telegram users should be rejected."""
        from unittest.mock import MagicMock, patch
        
        # Create a mock inactive user
        mock_user = MagicMock()
        mock_user.telegram_id = 987654321
        mock_user.role = "admin"
        mock_user.is_active = False
        
        # Mock the session's execute method
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_user
        mock_session.close = MagicMock()
        
        # Patch create_session where it's used
        with patch("execqueue.api.dependencies.create_session", return_value=mock_session):
            response = TestClient(app).post("/restart", headers={"X-Telegram-User-ID": "987654321"})

        assert response.status_code == 403
        assert "not active" in response.json()["detail"]

    def test_restart_rejects_unknown_telegram_user(self, monkeypatch):
        """Unknown Telegram users should be rejected."""
        from unittest.mock import MagicMock
        
        def mock_execute(query):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result
        
        mock_session = MagicMock()
        mock_session.execute = mock_execute
        
        from execqueue.api.dependencies import get_session
        import unittest.mock
        
        with unittest.mock.patch.object(get_session, '__call__', return_value=iter([mock_session])):
            response = TestClient(app).post("/restart", headers={"X-Telegram-User-ID": "999999999"})

        assert response.status_code == 403
        assert "not found" in response.json()["detail"]


class TestComponentHealthEndpoints:
    def test_db_endpoint_exists(self, monkeypatch):
        install_fake_healthchecks(monkeypatch)
        assert TestClient(app).get("/db/health").status_code == 200

    def test_api_health_endpoint_exists(self, monkeypatch):
        install_fake_healthchecks(monkeypatch)
        assert TestClient(app).get("/api/health").status_code == 200

    def test_opencode_health_endpoint_exists(self, monkeypatch):
        install_fake_healthchecks(monkeypatch, opencode_state="disabled", opencode_status="DEGRADED")
        response = TestClient(app).get("/opencode/health")

        assert response.status_code == 200
        assert response.json()["component"] == "opencode"
        assert response.json()["state"] == "disabled"

    def test_acp_restart_endpoint_is_not_available(self):
        response = TestClient(app).post("/api/system/acp/restart")
        assert response.status_code == 404


class TestHealthEndpointsInOpenAPI:
    def test_component_health_endpoints_in_openapi(self):
        payload = TestClient(app).get("/openapi.json").json()

        assert "/api/health" in payload["paths"]
        assert "/db/health" in payload["paths"]
        assert "/opencode/health" in payload["paths"]
        assert "/acp/health" not in payload["paths"]
