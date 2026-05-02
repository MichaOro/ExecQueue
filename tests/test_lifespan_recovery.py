"""Tests for FastAPI lifespan crash-recovery hook (REQ-017 P2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI

from execqueue.main import lifespan


@pytest.mark.asyncio
async def test_lifespan_recovery_calls_orchestrator():
    """The lifespan handler should invoke recover_running_workflows on startup."""
    app = FastAPI()

    with patch("execqueue.main.Orchestrator") as MockOrchestrator, \
         patch("execqueue.main.get_db_session") as mock_get_db:

        mock_orch = AsyncMock()
        MockOrchestrator.return_value = mock_orch

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_get_db.return_value = mock_cm

        async with lifespan(app):
            pass

        mock_orch.recover_running_workflows.assert_awaited_once_with(mock_session)


@pytest.mark.asyncio
async def test_lifespan_recovery_timeout_does_not_crash():
    """Lifespan should handle recovery timeout gracefully."""
    app = FastAPI()

    with patch("execqueue.main.Orchestrator") as MockOrchestrator, \
         patch("execqueue.main.get_db_session") as mock_get_db:

        mock_orch = AsyncMock()
        mock_orch.recover_running_workflows.side_effect = TimeoutError("Simulated timeout")
        MockOrchestrator.return_value = mock_orch

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_get_db.return_value = mock_cm

        # Should not raise
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_lifespan_recovery_error_does_not_crash():
    """Lifespan should handle recovery errors gracefully."""
    app = FastAPI()

    with patch("execqueue.main.Orchestrator") as MockOrchestrator, \
         patch("execqueue.main.get_db_session") as mock_get_db:

        mock_orch = AsyncMock()
        mock_orch.recover_running_workflows.side_effect = RuntimeError("DB error")
        MockOrchestrator.return_value = mock_orch

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_get_db.return_value = mock_cm

        # Should not raise
        async with lifespan(app):
            pass
