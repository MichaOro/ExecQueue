# REQ-011 — Quality Review, Scope Decision and Improvement Notes

## Kurzfazit
Die vorhandenen Arbeitspakete sind fachlich grundsätzlich brauchbar: Sie schneiden Statusmodell, Candidate Discovery, Batch Planning, Locking, Git-Kontext, Runner-Kontext, Recovery und Validierung sauber. Für maximale Umsetzungsqualität mussten jedoch vier Punkte geschärft werden:

1. **Scope-Grenze präzisieren:** REQ-011 endet bei *Execution Preparation / Runner Handoff*. OpenCode-Serve-Start, Prompt-Versand und `queued -> in_progress` gehören in eine nachgelagerte Execution-Phase.
2. **Status-Semantik härten:** `queued` darf nicht bedeuten „läuft schon“, sondern „atomar geclaimt und zur Vorbereitung/Übergabe vorgesehen“.
3. **Parallelisierung operationalisieren:** Read-only darf breit parallel laufen; Write darf nur über isolierte Branch-/Worktree-Kontexte parallel laufen; gleiche explizite Branches müssen serialisiert werden.
4. **Recovery und Side Effects trennen:** DB-Lock ist kurz und atomar. Git-/Filesystem-Seiteneffekte passieren danach und müssen recoverable/non-recoverable klassifiziert werden.

## Kritische Qualitätslücken im Original
| Bereich | Befund | Verbesserung |
|---|---|---|
| Scope | Arbeitspakete schließen TaskExecution/OpenCode teilweise aus, der PUML-Flow enthält sie aber. | Explizite Grenze eingeführt: REQ-011 liefert `PreparedExecutionContext`, startet aber keine OpenCode-Session. |
| Statusmodell | `queued` ist korrekt benannt, aber die Lifecycle-Bedeutung war nicht hart genug abgegrenzt. | State-Machine-Regeln und verbotene Übergänge ergänzt. |
| Batch Planning | Gute Grundidee, aber Batch-Arten und Claim-Reihenfolge waren nicht vollständig operationalisiert. | Drei Batch-Kategorien definiert: `readonly_parallel`, `write_parallel_isolated`, `write_sequential`. |
| Locking | Gute Trennung von Git und DB, aber Claim-Konflikte brauchen eindeutiges Verhalten. | Requery/Abort-Verhalten bei affected-row mismatch ergänzt. |
| Git-Kontext | Gute Sicherheitsprüfpunkte, aber Ownership/Reuse-Regeln brauchen harte Invarianten. | Worktree Ownership Guard, Root Guard und Dirty-State-Regeln ergänzt. |
| Runner-Kontext | Sinnvoll, aber Downstream-Kontrakt sollte als versioniertes DTO betrachtet werden. | `PreparedExecutionContext.v1` als handoff object ergänzt. |
| Recovery | Solide, aber Side-Effect-State muss Entscheidungsgrundlage sein. | Recovery Matrix ergänzt. |
| Validierung | E2E gut, aber Scope muss verhindern, dass OpenCode versehentlich startet. | Negative Assertions ergänzt: kein Prompt, kein Session-Start, kein `in_progress`. |

## Finale Scope-Entscheidung
REQ-011 implementiert **nur die Vorbereitung bis zum stabilen Handoff**:

```text
backlog -> queued -> prepared_context_available
```

Nicht enthalten:

```text
queued/prepared -> in_progress -> review/done/failed
```

Diese nachgelagerte Execution-Phase sollte als eigene Requirement-/Arbeitspaketserie geführt werden, weil sie andere Risiken enthält: OpenCode Serve Session Lifecycle, Prompt Dispatch, Event Streaming, Runner Heartbeats, Commit/Review und Ergebnisverarbeitung.

## Empfohlene Ausführungsreihenfolge
1. `01-status-and-task-metadata`
2. `02-trigger-and-candidate-discovery`
3. `03-classification-and-batch-planning`
4. `04-atomic-locking-and-queued-transition`
5. `05-write-git-context-preparation`
6. `06-readonly-and-prepared-context-contract`
7. `07-preparation-failure-and-stale-recovery`
8. `08-observability-and-e2e-validation`
9. `09-flow-alignment-and-documentation`

## Abhängigkeitsskizze
```text
01 ─┬─> 02 ─> 03 ─> 04 ─┬─> 05 ─┐
    │                    │       ├─> 06 ─> 08 ─> 09
    └────────────────────┴─> 07 ─┘
```
