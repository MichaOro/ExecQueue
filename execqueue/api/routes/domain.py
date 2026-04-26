"""Home for future tenant-aware domain endpoints.

Domain endpoints stay separate from technical system endpoints such as health
checks. When shared tenant scenarios are introduced, handlers in this router
can read ``X-Tenant-ID`` request-scoped through local FastAPI dependencies on
the concrete endpoint instead of relying on global middleware or app state.
"""

import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from execqueue.settings import get_settings

router = APIRouter(prefix="/api")

# Path to the global restart script
RESTART_SCRIPT = Path(__file__).parent.parent.parent.parent / "ops" / "scripts" / "global_restart.sh"


@router.post(
    "/system/restart",
    summary="Restart all system services (API and Telegram Bot)",
    operation_id="system_restart_post",
    responses={
        200: {"description": "Restart initiated successfully"},
        403: {"description": "Forbidden - Admin access required"},
        500: {"description": "Restart failed"},
    },
)
async def system_restart() -> dict:
    """Restart all system services (API and Telegram Bot).
    
    Executes the global_restart.sh script which restarts both the API and
    Telegram Bot services. This is an administrative operation.
    
    **Note**: This endpoint should be protected by authentication in production.
    Currently accessible to all callers (MVP).
    
    Returns:
        dict: Status of the restart operation
    """
    settings = get_settings()
    
    # Check if restart script exists
    if not RESTART_SCRIPT.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restart script not found: {RESTART_SCRIPT}",
        )
    
    try:
        # Execute restart script asynchronously (don't wait)
        # We use subprocess.Popen to start the restart in background
        # so the API response is returned immediately
        process = subprocess.Popen(
            [str(RESTART_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        
        # Don't wait for completion - restart happens in background
        # This allows the API to respond before it potentially restarts itself
        
        # Log the restart attempt (to file)
        log_file = Path(__file__).parent.parent.parent.parent / "ops" / "logs" / "api_restart_requests.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, "a") as f:
            f.write(f"[{process.pid}] Restart initiated via API\n")
        
        return {
            "status": "initiated",
            "message": "System restart initiated. API and Telegram Bot will restart.",
            "pid": process.pid,
        }
        
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Restart script not executable. Check permissions.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate restart: {str(exc)}",
        )
