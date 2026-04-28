# 08 — Observability and End-to-End Validation

## Ziel
Die Preparation-Phase mit strukturierten Logs, Korrelation und End-to-End-Tests absichern.

## Aufwand
Ca. 2h

## Scope
Enthalten:
- Strukturierte Logs/Events für REQ-011-Grenzen.
- Preparation-only E2E-Test.
- Negative Assertions gegen versehentlichen Execution-Start.

Nicht enthalten:
- Neues Observability-Framework.
- Grafana-/Metric-Produktivintegration, sofern kein bestehendes Pattern existiert.
- Downstream Execution Tests.

## Log-/Event-Felder
Mindestens:
- `task_id`
- `task_number`
- `task_type`
- `requirement_id`
- `correlation_id`
- `orchestrator_worker_id`
- `batch_id`
- `batch_type`
- `status_from`
- `status_to`
- `runner_mode`
- `branch_name`
- `worktree_path`
- `error_code`
- `error_class`

## E2E-Validierung
Preparation-only Szenario:
1. Task erstellen.
2. Trigger auslösen.
3. Candidate Discovery lädt Task.
4. Klassifikation und Batch Planning.
5. Atomic Locking nach `queued`.
6. Write-Task: Branch/Worktree/SHA vorbereitet.
7. Read-only Task: Base-Repo-Kontext vorbereitet.
8. `PreparedExecutionContext.v1` erzeugt.

Negative Assertions:
- Kein OpenCode Serve Start.
- Kein Prompt Dispatch.
- Kein `TaskExecution` Start, falls nicht explizit Teil des Handoff-Modells.
- Kein Status `in_progress`.
- Keine Commit-Erzeugung nach Execution, da Execution nicht läuft.

## Umsetzungsschritte
1. Bestehende Logging-Konvention prüfen.
2. Minimalen strukturierten Log-Standard ergänzen.
3. Preparation-only E2E-Test aufsetzen.
4. Write- und Read-only-Pfad validieren.
5. Negative Assertions ergänzen.
6. Testdokumentation aktualisieren.

## Akzeptanzkriterien
- Preparation-Flow ist anhand strukturierter Logs nachvollziehbar.
- Correlation-ID und Batch-ID sind über alle Schritte konsistent.
- E2E-Test deckt Write- und Read-only-Pfad ab.
- Kein Test oder Flow startet OpenCode Serve in REQ-011.
- Kein Task wechselt in REQ-011 nach `in_progress`.

## Risiken / Prüfpunkte
- Keine Assertions auf fragile Log-Texte, sondern strukturierte Felder.
- Git-Operationen in Tests isolieren oder sauber fixturen.
- Observability nicht als neues Framework bauen.

## Modellrouting
`[QWN]` — test-/loglastig, geringe Architekturambiguität.
