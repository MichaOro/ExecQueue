# 01 — Status and Task Metadata Foundation

## Ziel
`queued` als gültigen Task-Status etablieren und die minimalen Metadaten für Claiming, Preparation, Recovery und Handoff bereitstellen.

## Aufwand
Ca. 2h

## Scope
Enthalten:
- Status `queued` ergänzen.
- Metadaten für Locking/Recovery prüfen oder ergänzen.
- Statusvalidierung, DB-Constraints und Indexe aktualisieren.

Nicht enthalten:
- Candidate Discovery.
- Locking-Implementierung.
- Git-/Worktree-Erzeugung.
- Runner-/OpenCode-Start.

## Fachliche Semantik
`queued` bedeutet: Der Task wurde vom Orchestrator atomar geclaimt und ist für Preparation/Handoff reserviert. `queued` bedeutet **nicht**, dass OpenCode bereits läuft.

Erlaubte Statusübergänge in REQ-011:
- `backlog -> queued`
- `queued -> backlog` nur bei recoverable Preparation-Fehler ohne unsafe Side Effects
- `queued -> failed` bei non-recoverable Fehler oder Retry Exhaustion

Verboten in REQ-011:
- `queued -> in_progress`
- `queued -> review`
- `queued -> done`

## Technical Specification
- `TaskStatus.QUEUED = "queued"` ergänzen.
- Statusvalidierung/DB-Constraint/API-Schema/UI-Enum um `queued` erweitern.
- Minimalfelder prüfen, nicht blind duplizieren:
  - `queued_at`
  - `locked_by` oder `claimed_by`
  - `preparation_attempt_count`
  - `last_preparation_error`
  - `branch_name`
  - `worktree_path`
  - `commit_sha_before`
  - optional `prepared_context_version`
- Indexe prüfen/ergänzen:
  - executable candidates: `status`, `priority`, `order_index`, `created_at`
  - stale recovery: `status`, `queued_at`, `preparation_attempt_count`

## Umsetzungsschritte
1. Alle Statusdefinitionen lokalisieren.
2. `queued` in Enum/String-Literals/DB-Constraints ergänzen.
3. Minimalfelder gegen bestehendes Modell prüfen.
4. Fehlende Felder über vorhandene Migrationstechnik ergänzen.
5. Indexe konservativ ergänzen, sofern Query-Pfade sie benötigen.
6. Status- und Migrationstests ergänzen.

## Akzeptanzkriterien
- `queued` ist überall gültig, wo Task-Status validiert wird.
- `backlog -> queued` ist technisch möglich.
- Kein bestehender Execution-Start wird allein durch `queued` ausgelöst.
- Recovery-Felder sind vorhanden oder bewusst als nicht erforderlich dokumentiert.
- Tests beweisen, dass `queued -> in_progress` in REQ-011 nicht stattfindet.

## Risiken / Prüfpunkte
- Statuswerte können in API, UI, Tests und DB mehrfach dupliziert sein.
- Zu viele neue Felder würden das Modell unnötig aufblähen.
- Branch-/Worktree-Felder gehören nur dann auf `Task`, wenn sie über die Preparation hinaus Task-bezogen benötigt werden; sonst gehört der Kontext in ein Handoff-/Execution-Kontextobjekt.

## Modellrouting
`[QWN]` — pattern-nah, begrenzte Architekturambiguität.
