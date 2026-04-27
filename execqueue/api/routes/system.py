"""System-level routes that stay tenant-neutral."""

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from execqueue.api.routes.health import router as health_router

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(health_router)

SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "ops" / "scripts"
LOGS_DIR = Path(__file__).parent.parent.parent.parent / "ops" / "logs"

RESTART_SCRIPT = SCRIPTS_DIR / "global_restart.sh"
API_RESTART_SCRIPT = SCRIPTS_DIR / "api_restart.sh"
TELEGRAM_RESTART_SCRIPT = SCRIPTS_DIR / "telegram_restart.sh"
ACP_RESTART_SCRIPT = SCRIPTS_DIR / "acp_restart.sh"


def _execute_restart_script(
    script_path: Path, service_name: str, log_filename: str
) -> dict[str, object]:
    """Execute a restart script asynchronously and log the request."""
    if not script_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restart script not found: {script_path}",
        )

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        process = subprocess.Popen(
            [str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )

        log_file = LOGS_DIR / log_filename
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(log_file, "a", encoding="utf-8") as file_handle:
            file_handle.write(
                f"[{timestamp}] PID {process.pid} - "
                f"{service_name} restart initiated via API\n"
            )

        logger.info(
            "%s restart initiated via API",
            service_name,
            extra={"pid": process.pid, "script": str(script_path)},
        )

        return {
            "status": "initiated",
            "message": f"{service_name} restart initiated.",
            "pid": process.pid,
        }

    except PermissionError:
        logger.error("%s restart script not executable: %s", service_name, script_path)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Restart script not executable. Check permissions.",
        )
    except Exception as exc:
        logger.error(
            "Failed to initiate %s restart: %s",
            service_name,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate restart: {str(exc)}",
        )


@router.post(
    "/api/system/restart",
    summary="Restart all system services (API and Telegram Bot)",
    operation_id="system_restart_post",
    tags=["System"],
    responses={
        200: {"description": "Restart initiated successfully"},
        403: {"description": "Forbidden - Admin access required"},
        500: {"description": "Restart failed"},
    },
)
async def system_restart() -> dict[str, object]:
    """Restart all system services (API and Telegram Bot)."""
    return _execute_restart_script(
        script_path=RESTART_SCRIPT,
        service_name="System (API + Telegram Bot)",
        log_filename="system_restart_requests.log",
    )


@router.post(
    "/api/restart",
    summary="Restart API service only",
    operation_id="api_restart_post",
    tags=["System"],
    responses={
        200: {"description": "Restart initiated successfully"},
        403: {"description": "Forbidden - Admin access required"},
        500: {"description": "Restart failed"},
    },
)
async def api_restart() -> dict[str, object]:
    """Restart the API service only."""
    return _execute_restart_script(
        script_path=API_RESTART_SCRIPT,
        service_name="API",
        log_filename="api_restart_requests.log",
    )


@router.post(
    "/api/telegram_bot/restart",
    summary="Restart Telegram Bot service only",
    operation_id="telegram_bot_restart_post",
    tags=["System"],
    responses={
        200: {"description": "Restart initiated successfully"},
        403: {"description": "Forbidden - Admin access required"},
        500: {"description": "Restart failed"},
    },
)
async def telegram_bot_restart() -> dict[str, object]:
    """Restart the Telegram Bot service only."""
    return _execute_restart_script(
        script_path=TELEGRAM_RESTART_SCRIPT,
        service_name="Telegram Bot",
        log_filename="telegram_restart_requests.log",
    )


@router.post(
    "/api/system/acp/restart",
    summary="Restart ACP service only",
    operation_id="acp_restart_post",
    tags=["System"],
    responses={
        200: {"description": "ACP restart initiated successfully"},
        403: {"description": "Forbidden - Admin access required"},
        500: {"description": "ACP restart failed"},
    },
)
async def acp_restart() -> dict[str, object]:
    """Restart the ACP (OpenCode ACP) service only."""
    return _execute_restart_script(
        script_path=ACP_RESTART_SCRIPT,
        service_name="ACP",
        log_filename="acp_restart_requests.log",
    )
