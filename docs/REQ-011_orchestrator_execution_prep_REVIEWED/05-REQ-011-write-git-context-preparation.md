# 05 — Write Task Branch and Worktree Preparation

## Ziel
Für gequeue-te Write-Tasks einen sicheren Branch-/Worktree-Kontext vorbereiten und den pre-execution Commit-SHA erfassen.

## Aufwand
Ca. 2h

## Scope
Enthalten:
- Branch-Auflösung oder Branch-Erzeugung.
- Worktree-Erzeugung oder sichere Wiederverwendung.
- Root-/Ownership-/Dirty-State-Guards.
- `commit_sha_before` erfassen.

Nicht enthalten:
- DB-Lock.
- OpenCode-Start.
- Commit nach Ausführung.
- Merge/Review.

## Sicherheitsinvarianten
- Keine destructive Git-Kommandos.
- Keine existierenden Branches überschreiben.
- Kein Worktree außerhalb des konfigurierten Worktree-Roots.
- Wiederverwendung nur, wenn der Worktree eindeutig diesem Task gehört und sauber/erwartbar ist.
- Git-Operationen laufen nach erfolgreichem DB-Lock, aber außerhalb der Lock-Transaktion.

## Technical Specification
- Branch-Naming bei fehlender Branch:
  - `execqueue/task-{task_number}-{short_task_id}`
  - Git-Ref-Validierung über vorhandenen Git-Wrapper oder `git check-ref-format`.
- Worktree-Pfad:
  - unter konfiguriertem `worktree_root`
  - canonical path check gegen Root Escape
  - keine User-Eingaben direkt in Pfade übernehmen
- Reuse-Regeln:
  - `worktree_path` existiert
  - liegt unter Root
  - gehört laut gespeicherter Task-ID/Branch zu diesem Task
  - ist nicht dirty, außer System definiert explizit erlaubten Zustand
- Persistieren oder Handoff vorbereiten:
  - `branch_name`
  - `worktree_path`
  - `commit_sha_before`
  - optional `git_context_prepared_at`

## Umsetzungsschritte
1. Speicherort für Branch/Worktree/SHA klären.
2. Worktree-Root-Konfiguration ermitteln.
3. Branch-Naming und Git-Ref-Validierung implementieren.
4. Worktree-Pfadgenerierung mit Root Guard implementieren.
5. Git-Kommandos mit Timeout kapseln.
6. Existing-Worktree-Reuse-Regeln implementieren.
7. Fehler typed klassifizieren: recoverable, conflict, non-recoverable.

## Akzeptanzkriterien
- Jeder vorbereitete Write-Task besitzt Branch, Worktree und `commit_sha_before`.
- Branch-Namen sind deterministisch und valide.
- Worktree-Pfade können den Root nicht verlassen.
- Ungültige oder fremde Worktrees werden nicht wiederverwendet.
- Git-Timeouts und Git-Fehler werden strukturiert gemeldet.

## Risiken / Prüfpunkte
- Halberstellte Worktrees nicht blind löschen; Cleanup nur bei eindeutig task-owned Artefakten.
- Explizite Branches mehrerer Tasks müssen vorab durch Paket 03 serialisiert sein.
- Keine Remote-Push-/Fetch-Policy einführen, wenn sie nicht bereits Systemstandard ist.

## Modellrouting
`[GPT]` — hohe Seiteneffekt- und Security-Relevanz.
