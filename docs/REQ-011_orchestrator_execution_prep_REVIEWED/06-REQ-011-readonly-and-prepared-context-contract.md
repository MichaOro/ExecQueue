# 06 — Read-only and Prepared Execution Context Contract

## Ziel
Read-only Tasks ohne Branch-/Worktree-Mutation vorbereiten und einen versionierten, serialisierbaren `PreparedExecutionContext` für die nachgelagerte Execution-Phase bereitstellen.

## Aufwand
Ca. 2h

## Scope
Enthalten:
- Read-only Kontextbildung.
- Write-Kontext aus Paket 05 in gemeinsames DTO mappen.
- Kontextvalidierung.
- Secret Guard.

Nicht enthalten:
- TaskExecution erzeugen.
- Runner-ID speichern.
- OpenCode Serve Session starten.
- Prompt versenden.
- Status `in_progress` setzen.

## Kontextvertrag
`PreparedExecutionContext.v1` enthält nur Daten, die der nachgelagerte Runner braucht, um eine Execution kontrolliert zu starten.

Pflichtfelder:
- `version`
- `task_id`
- `task_number`
- `task_type`
- `requires_write_access`
- `parallelization_mode`
- `runner_mode`: `read_only` oder `write`
- `base_repo_path`
- `branch_name` nullable für read-only
- `worktree_path` nullable für read-only
- `commit_sha_before` nullable für read-only
- `correlation_id`
- `batch_id`

Validierungsregeln:
- `runner_mode = write` erfordert `branch_name`, `worktree_path`, `commit_sha_before`.
- `runner_mode = read_only` darf keine Branch-/Worktree-Erzeugung auslösen.
- `base_repo_path` muss validiert sein.
- Kontext darf keine Tokens, Secrets oder Provider-Keys enthalten.

## Umsetzungsschritte
1. Downstream-Kontextbedarf gegen vorhandenes TaskExecution-/Runner-Modell prüfen.
2. `PreparedExecutionContext.v1` als DTO/Schema definieren.
3. Read-only Context Builder implementieren.
4. Write-Kontext-Mapping aus Paket 05 anbinden.
5. Kontextvalidierung ergänzen.
6. JSON-Serialisierungs- und Secret-Guard-Tests ergänzen.

## Akzeptanzkriterien
- Read-only Tasks erzeugen keine Branches oder Worktrees.
- Read-only Tasks erhalten `runner_mode = read_only` und validen `base_repo_path`.
- Write Tasks erhalten `runner_mode = write`, Branch, Worktree und `commit_sha_before`.
- Kontext ist JSON-serialisierbar.
- Kontext enthält keine Secrets.
- Kein Code in diesem Paket startet OpenCode oder setzt `in_progress`.

## Risiken / Prüfpunkte
- Read-only bedeutet nicht „keine operativen DB-Schreibungen“; Logs/Status/Events bleiben erlaubt.
- Kontextvalidierung soll Fehler vor dem Runner sichtbar machen.
- DTO-Versionierung verhindert spätere stille Contract-Breaks.

## Modellrouting
`[QWN]` — klarer DTO-/Validation-Schnitt.
