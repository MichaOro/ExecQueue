"""Tests for the Telegram bot API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execqueue.workers.telegram.api_client import TelegramAPIClient


@pytest.mark.asyncio
async def test_create_task_uses_current_api_contract():
    client = TelegramAPIClient()
    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {"task_number": 41, "status": "backlog"}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        success, message = await client.create_task(
            task_type="planning",
            prompt="Summarize the release",
            created_by_ref="123456",
        )

    assert success is True
    assert message == "Aufgabe #41 wurde erstellt."
    mock_client.post.assert_called_once_with(
        f"{client.base_url}/api/task",
        json={
            "type": "planning",
            "prompt": "Summarize the release",
            "created_by_type": "user",
            "created_by_ref": "123456",
        },
    )


@pytest.mark.asyncio
async def test_create_requirement_includes_title():
    client = TelegramAPIClient()
    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {"task_number": 42, "status": "backlog"}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        success, message = await client.create_task(
            task_type="requirement",
            prompt="Capture the requirement details",
            created_by_ref="123456",
            title="REQ-42",
        )

    assert success is True
    assert message == "Aufgabe #42 wurde erstellt."
    mock_client.post.assert_called_once_with(
        f"{client.base_url}/api/task",
        json={
            "type": "requirement",
            "prompt": "Capture the requirement details",
            "created_by_type": "user",
            "created_by_ref": "123456",
            "title": "REQ-42",
        },
    )


@pytest.mark.asyncio
async def test_create_requirement_requires_title_before_network_call():
    client = TelegramAPIClient()

    with patch("httpx.AsyncClient") as mock_client_class:
        success, message = await client.create_task(
            task_type="requirement",
            prompt="Capture the requirement details",
            created_by_ref="123456",
        )

    assert success is False
    assert message == "Requirement-Titel darf nicht leer sein."
    mock_client_class.assert_not_called()


@pytest.mark.asyncio
async def test_get_task_status_maps_not_found_to_simple_message():
    client = TelegramAPIClient()
    response = MagicMock()
    response.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        success, message = await client.get_task_status(999)

    assert success is False
    assert message == "Aufgabe nicht gefunden."


@pytest.mark.asyncio
async def test_create_task_maps_validation_error_to_simple_message():
    client = TelegramAPIClient()
    response = MagicMock()
    response.status_code = 422

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        success, message = await client.create_task(
            task_type="incident",
            prompt="Bad payload",
            created_by_ref="123456",
        )

    assert success is False
    assert message == "Ungueltige Eingabe. Bitte pruefen Sie Ihre Angaben."


@pytest.mark.asyncio
async def test_get_task_status_maps_unexpected_api_error_detail():
    client = TelegramAPIClient()
    response = MagicMock()
    response.status_code = 500
    response.json.return_value = {"detail": "Database temporarily unavailable."}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        success, message = await client.get_task_status(17)

    assert success is False
    assert message == "Database temporarily unavailable."
