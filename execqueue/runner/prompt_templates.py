"""Prompt templates for OpenCode dispatch.

This module provides prompt templates for converting PreparedExecutionContext
into OpenCode prompts with proper read-only/write semantics per REQ-012-05.
"""

from __future__ import annotations


def build_readonly_prompt(context: dict) -> str:
    """Build prompt for read-only task execution.

    Args:
        context: PreparedExecutionContext as dictionary

    Returns:
        Formatted prompt string
    """
    task_number = context.get("task_number", "Unknown")
    task_type = context.get("task_type", "analysis")
    base_repo_path = context.get("base_repo_path", ".")

    return f"""## Task {task_number} - Read-Only {task_type.title()}

### Ziel
Fuhre eine {task_type} Aufgabe durch, OHNE den Codebase zu andern.

### Scope
- Repository: {base_repo_path}
- Modus: READ-ONLY (keine Schreiboperationen)

### Wichtige Regeln
1. **KEINE Dateien andern** - Dies ist eine reine Analyse/Auswertungs-Aufgabe
2. **KEINE Git-Commits** - Keine Änderungen vornehmen
3. **KEINE Worktree-Operationen** - Nutze den bestehenden Zustand
4. Ausgabe ist rein informierend (Report, Analyse, Planung)

### Erwartetes Ergebnis
- Detaillierte Dokumentation der Analyse/Ergebnisse
- Keine Code-Änderungen
- Keine Commit-Historie-Änderungen

### Akzeptanzkriterien
- Alle Analyse-Schritte wurden durchgefuhrt
- Ergebnisse sind nachvollziehbar dokumentiert
- Keine Dateien wurden geändert
"""


def build_write_prompt(context: dict) -> str:
    """Build prompt for write task execution.

    Args:
        context: PreparedExecutionContext as dictionary

    Returns:
        Formatted prompt string
    """
    task_number = context.get("task_number", "Unknown")
    task_type = context.get("task_type", "execution")
    branch_name = context.get("branch_name", "unknown")
    worktree_path = context.get("worktree_path", ".")
    commit_sha_before = context.get("commit_sha_before", "unknown")

    return f"""## Task {task_number} - Write {task_type.title()}

### Ziel
Fuhre die {task_type} Aufgabe durch und erstelle einen nachvollziehbaren Commit.

### Scope
- Repository: {worktree_path}
- Branch: {branch_name}
- Start-Commit: {commit_sha_before}
- Modus: WRITE (Schreiboperationen erlaubt)

### Wichtige Regeln
1. **Nur im Worktree andern** - Alle Änderungen mussen in {worktree_path} erfolgen
2. **Keine destruktiven Git-Operationen** - Kein force-push, kein hard-reset
3. **Genau EIN Commit** - Sofern nicht anders gefordert:
   - Alle Änderungen in einem Commit zusammenfassen
   - Klare, aussagekräftige Commit-Message
   - Commit muss nachvollziehbar sein
4. **Validierung vor Commit** - Fuhre aus:
   - `git status` - Prüfe auf ungewollte Änderungen
   - `git diff` - Review der Änderungen
   - Test-Suite ausfuhren (falls vorhanden)

### Commit-Erwartung
- Branch: {branch_name}
- Alle Änderungen im Worktree {worktree_path}
- Ein sauberer Commit mit aussagekräftiger Message
- Keine destruktiven Operationen

### Akzeptanzkriterien
- Alle geforderten Änderungen wurden durchgefuhrt
- Tests bestehen (falls vorhanden)
- Ein sauberer Commit wurde erstellt
- Keine ungewollten Änderungen
- Keine destruktiven Git-Operationen
"""


def build_prompt(context: dict) -> str:
    """Build prompt based on context runner mode.

    Args:
        context: PreparedExecutionContext as dictionary

    Returns:
        Formatted prompt string

    Raises:
        ValueError: If runner_mode is unknown
    """
    runner_mode = context.get("runner_mode", "write")

    if runner_mode == "read_only":
        return build_readonly_prompt(context)
    elif runner_mode == "write":
        return build_write_prompt(context)
    else:
        raise ValueError(f"Unknown runner_mode: {runner_mode}")
