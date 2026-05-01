"""API client for bot to FastAPI communication."""

from __future__ import annotations

import httpx
import logging

from execqueue.settings import get_settings

logger = logging.getLogger(__name__)


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
        title: str | None = None,
        branch: str | None = None,
    ) -> tuple[bool, str]:
        """Create a task via the internal API.
        
        Args:
            task_type: Type of task (planning/execution/analysis/requirement)
            prompt: Task content/prompt
            created_by_ref: Creator identifier (Telegram user ID)
            title: Requirement title (if requirement type)
            branch: Branch name to associate with task (optional)
            
        Returns:
            (success: bool, message: str)
        """
        url = f"{self.base_url}/api/task"
        payload = {
            "type": task_type,
            "prompt": prompt,
            "created_by_type": "user",
            "created_by_ref": created_by_ref,
        }
        if task_type == "requirement":
            normalized_title = title.strip() if title else ""
            if not normalized_title:
                return False, "Requirement-Titel darf nicht leer sein."
            payload["title"] = normalized_title

        # Include branch if provided
        if branch:
            payload["branch_name"] = branch

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
                # Check if validation error is about branch
                error_detail = _read_error_detail(response)
                if error_detail and "branch" in error_detail.lower():
                    return False, f"Branch-Fehler: {error_detail}"
                return False, "Ungueltige Eingabe. Bitte pruefen Sie Ihre Angaben."

            error_detail = _read_error_detail(response)
            return False, error_detail or "Die Aufgabe konnte nicht erstellt werden."
        except httpx.TimeoutException:
            return False, "Zeitueberschreitung bei der Anfrage. Bitte erneut versuchen."
        except httpx.ConnectError:
            return False, "Verbindung zum Server nicht moeglich. Bitte Server-Status pruefen."
        except Exception:
            logger.exception("Unexpected error creating task with branch %s", branch)
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
