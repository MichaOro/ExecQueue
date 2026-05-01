"""Git helper module for read-only Git operations.

This module provides safe, read-only Git functions for branch queries and validation.
It is designed to be used by the Telegram Bot to retrieve branch information without
modifying the repository.

All functions are read-only and do not modify the repository state.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List


class GitHelperError(Exception):
    """Base exception for Git helper errors."""
    pass


class GitRepositoryError(GitHelperError):
    """Raised when the repository is not accessible or invalid."""
    pass


class GitTimeoutError(GitHelperError):
    """Raised when a Git operation times out."""
    pass


def get_local_branches(
    repo_path: Path | None = None,
    timeout: int = 5
) -> List[str]:
    """Get a list of all local branches in the repository.
    
    Args:
        repo_path: Path to the Git repository. If None, uses the current directory.
        timeout: Timeout in seconds for the Git command (default: 5).
    
    Returns:
        List of branch names (without the "* " prefix for current branch).
        Returns an empty list if no branches exist or on error.
    
    Raises:
        GitRepositoryError: If the repository is not accessible or not a Git repo.
        GitTimeoutError: If the Git command times out.
    """
    if repo_path is None:
        repo_path = Path.cwd()
    else:
        repo_path = Path(repo_path).resolve()
    
    if not repo_path.exists():
        raise GitRepositoryError(f"Repository path does not exist: {repo_path}")
    
    try:
        result = subprocess.run(
            ["git", "branch", "--list"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise GitTimeoutError(f"Git command timed out after {timeout} seconds") from e
    
    if result.returncode != 0:
        error_detail = result.stderr.strip() or "unknown error"
        raise GitRepositoryError(f"Failed to list branches: {error_detail}")
    
    # Parse output: each line is "* branchname" for current or "  branchname" for others
    branches = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        # Remove the "* " prefix for current branch or "  " for others
        branch_name = line.lstrip("* ").strip()
        if branch_name:
            branches.append(branch_name)
    
    return branches


def get_current_branch(
    repo_path: Path | None = None,
    timeout: int = 5,
) -> str:
    """Return the currently active local branch name.

    Args:
        repo_path: Path to the Git repository. If None, uses the current directory.
        timeout: Timeout in seconds for the Git command.

    Returns:
        The current branch name.

    Raises:
        GitRepositoryError: If the repository is not accessible, detached, or invalid.
        GitTimeoutError: If the Git command times out.
    """
    if repo_path is None:
        repo_path = Path.cwd()
    else:
        repo_path = Path(repo_path).resolve()

    if not repo_path.exists():
        raise GitRepositoryError(f"Repository path does not exist: {repo_path}")

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise GitTimeoutError(f"Git command timed out after {timeout} seconds") from e

    if result.returncode != 0:
        error_detail = result.stderr.strip() or "unknown error"
        raise GitRepositoryError(f"Failed to determine current branch: {error_detail}")

    branch_name = result.stdout.strip()
    if not branch_name or branch_name == "HEAD":
        raise GitRepositoryError(
            "Failed to determine current branch: repository is in detached HEAD state"
        )

    return branch_name


def validate_branch_name(name: str) -> bool:
    """Validate a branch name according to Git ref rules.
    
    Args:
        name: The branch name to validate.
    
    Returns:
        True if the branch name is valid, False otherwise.
    
    Valid branch names:
    - Cannot contain spaces, tildes, carets, colons, question marks, asterisks, or brackets
    - Cannot start or end with a slash
    - Cannot contain two consecutive dots
    - Cannot contain ASCII control characters or backslashes
    - Cannot end with ".lock"
    """
    if not name:
        return False
    
    # Basic length check
    if len(name) > 255:
        return False
    
    # Check for invalid characters and patterns
    # Git ref patterns that are not allowed
    invalid_patterns = [
        r"\s",           # whitespace
        r"~",            # tilde
        r"\^",           # caret
        r":",            # colon
        r"\?",           # question mark
        r"\*",           # asterisk
        r"\[",           # opening bracket
        r"\]",           # closing bracket
        r"@@@",          # at signs
        r"\\\\",         # backslash
        r"\.\.",         # two consecutive dots
        r"/$",           # ending with slash
        r"^/",           # starting with slash
        r"\.lock$",      # ending with .lock
    ]
    
    for pattern in invalid_patterns:
        if re.search(pattern, name):
            return False
    
    # Cannot start with a dash
    if name.startswith("-"):
        return False
    
    # Must not contain control characters (ASCII 0-31 and 127)
    for char in name:
        if ord(char) < 32 or ord(char) == 127:
            return False
    
    return True


def branch_exists(
    branch_name: str,
    repo_path: Path | None = None,
    timeout: int = 5
) -> bool:
    """Check if a branch exists in the repository.
    
    Args:
        branch_name: The name of the branch to check.
        repo_path: Path to the Git repository. If None, uses the current directory.
        timeout: Timeout in seconds for the Git command (default: 5).
    
    Returns:
        True if the branch exists (local or remote), False otherwise.
    
    Raises:
        GitRepositoryError: If the repository is not accessible or not a Git repo.
        GitTimeoutError: If the Git command times out.
    """
    if repo_path is None:
        repo_path = Path.cwd()
    else:
        repo_path = Path(repo_path).resolve()
    
    if not repo_path.exists():
        raise GitRepositoryError(f"Repository path does not exist: {repo_path}")
    
    # First validate the branch name
    if not validate_branch_name(branch_name):
        return False
    
    try:
        # Check both local and remote branches
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise GitTimeoutError(f"Git command timed out after {timeout} seconds") from e
    
    # If that fails, try with refs/heads/ prefix for local branches
    if result.returncode != 0:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise GitTimeoutError(f"Git command timed out after {timeout} seconds") from e
    
    return result.returncode == 0


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
    if repo_path is None:
        repo_path = Path.cwd()
    else:
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
    
    return True, f"Branch '{branch_name}' erfolgreich erstellt."
