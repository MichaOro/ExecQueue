"""API client for bot to FastAPI communication."""

from __future__ import annotations

import httpx

from execqueue.settings import get_settings


class TelegramAPIClient:
    """Client for bot to FastAPI communication."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = (
            f"http://{settings.execqueue_api_host}:{settings.execqueue_api_port}"
        )
        self.timeout = 10.0

    async def create_task(
        self,
        task_type: str,
        prompt: str,
        created_by_ref: str,
    ) -> tuple[bool, str]:
        """Create a task via the internal API."""
        url = f"{self.base_url}/api/task"
        payload = {
            "type": task_type,
            "prompt": prompt,
            "created_by_type": "user",
            "created_by_ref": created_by_ref,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)

            if response.status_code == 201:
                data = response.json()
                task_number = data.get("task_number")
                if task_number is None:
                    return True, "Aufgabe erfolgreich erstellt."
                return True, f"Aufgabe #{task_number} wurde erstellt."

            if response.status_code == 422:
                return False, "Ungueltige Eingabe. Bitte pruefen Sie Ihre Angaben."

            error_detail = _read_error_detail(response)
            return False, error_detail or "Die Aufgabe konnte nicht erstellt werden."
        except httpx.TimeoutException:
            return False, "Zeitueberschreitung bei der Anfrage. Bitte erneut versuchen."
        except Exception:
            return False, "Verbindungsfehler zum Server."

    async def get_task_status(self, task_number: int) -> tuple[bool, str | dict]:
        """Get task status via the internal API."""
        url = f"{self.base_url}/api/task/{task_number}/status"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)

            if response.status_code == 200:
                return True, response.json()

            if response.status_code == 404:
                return False, "Aufgabe nicht gefunden."

            error_detail = _read_error_detail(response)
            return False, error_detail or "Status konnte nicht geladen werden."
        except httpx.TimeoutException:
            return False, "Zeitueberschreitung bei der Anfrage."
        except Exception:
            return False, "Verbindungsfehler zum Server."


def _read_error_detail(response: httpx.Response) -> str | None:
    """Extract a simple string detail from an API response."""
    try:
        detail = response.json().get("detail")
    except Exception:
        return None

    if isinstance(detail, str):
        detail = detail.strip()
        if detail:
            return detail

    return None


api_client = TelegramAPIClient()
