"""Git write operations for branch creation.

This module contains write operations for Git that modify the repository state.
It is separated from the read-only operations in git_helper.py for better
architectural separation and security considerations.

WARNING: Functions in this module can modify the repository state.
They should be used with appropriate authorization and logging.
"""

from __future__ import annotations

import logging
from pathlib import Path

from execqueue.workers.telegram.git_helper import (
    GitHelperError,
    GitRepositoryError,
    GitTimeoutError,
    branch_exists,
    validate_branch_name,
)

logger = logging.getLogger(__name__)


def create_branch(
    branch_name: str,
    repo_path: Path | None = None,
    timeout: int = 5
) -> tuple[bool, str]:
    """Create a new branch - READ-WRITE operation.

    Erstellt einen neuen Branch am aktuellen HEAD. Fuehrt KEIN checkout durch.

    Args:
        branch_name: Name fuer den neuen Branch
        repo_path: Pfad zum Git Repository (default: cwd)
        timeout: Command timeout in Sekunden

    Returns:
        (success: bool, message: str)
        - On success: (True, "Branch 'name' erfolgreich erstellt")
        - On failure: (False, "Error detail")

    Raises:
        GitRepositoryError: Wenn Repository nicht zugreifbar
        GitTimeoutError: Wenn Git-Command timeoutet
    """
    import subprocess

    if repo_path is None:
        repo_path = Path.cwd()

    repo_path = Path(repo_path).resolve()

    if not repo_path.exists():
        return False, f"Repository nicht gefunden: {repo_path}"

    # 1. Branch-Name validieren
    if not validate_branch_name(branch_name):
        return False, (
            f"Ungueltiger Branch-Name '{branch_name}'. "
            "Bitte keine Leerzeichen, ~, ^, :, ?, *, [] verwenden. "
            "Nicht mit / oder - beginnen oder mit .lock enden."
        )

    # 2. Pruefen ob Branch bereits existiert
    if branch_exists(branch_name, repo_path, timeout):
        return False, f"Branch '{branch_name}' existiert bereits."

    # 3. Branch erstellen (ohne checkout)
    try:
        result = subprocess.run(
            ["git", "branch", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"Git-Operation zeitueberschritten nach {timeout} Sekunden."

    if result.returncode != 0:
        error_detail = result.stderr.strip() or "unbekannter Fehler"
        # Fuer Detached HEAD oder andere spezifische Fehler
        if "detached" in error_detail.lower():
            return False, (
                "Repository befindet sich in Detached HEAD State. "
                "Bitte zuerst auf existierenden Branch wechseln."
            )
        return False, f"Branch-Erstellung fehlgeschlagen: {error_detail[:100]}"

    logger.info("Branch '%s' erfolgreich erstellt in %s", branch_name, repo_path)
    return True, f"Branch '{branch_name}' erfolgreich erstellt."
