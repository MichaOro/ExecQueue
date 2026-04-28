# 04 — Atomic Locking and Queued Transition

## Ziel
Geplante Tasks atomar claimen und im selben DB-Schritt von `backlog` nach `queued` überführen, ohne Git-/Filesystem-Operationen in der Lock-Transaktion auszuführen.

## Aufwand
Ca. 2h

## Scope
Enthalten:
- Atomic Claim.
- `backlog -> queued`.
- Conflict Handling.
- Worker-/Batch-Korrelation.

Nicht enthalten:
- Candidate Query.
- Klassifikation.
- Git-Kontext.
- OpenCode-/Runner-Start.

## Concurrency-Invariante
Zwei Orchestrator-Worker dürfen niemals denselben Task erfolgreich claimen. Bei Konflikt wird der geplante Batch verworfen und über Candidate Discovery neu aufgebaut.

## Technical Specification
- Funktion `lock_selected_tasks(plan, worker_id, batch_id)`.
- Nur Tasks mit aktuellem `status = backlog` dürfen aktualisiert werden.
- Atomar setzen:
  - `status = queued`
  - `queued_at = now`
  - `locked_by = worker_id`
  - `updated_at = now`
  - optional `batch_id`
- Affected-row-count muss exakt zur erwarteten Task-Anzahl passen.
- Bei mismatch:
  - Transaction rollback oder konfliktfrei abbrechen
  - kein partieller Git-/Preparation-Start
  - Requery-Signal zurückgeben
- PostgreSQL bevorzugt: `FOR UPDATE SKIP LOCKED` oder atomic `UPDATE ... WHERE status='backlog' ... RETURNING`.
- SQLite/Testfallback nur so weit unterstützen, wie Tests deterministisch bleiben.

## Umsetzungsschritte
1. DB-Engine und bestehende Transaktionspatterns prüfen.
2. Lock-Funktion implementieren.
3. Atomic Status-/Metadatenupdate implementieren.
4. Affected-row-count validieren.
5. Konfliktpfad als typed result modellieren.
6. Concurrency-Tests ergänzen.

## Akzeptanzkriterien
- Zwei Worker claimen denselben Task nicht doppelt.
- Nur `backlog`-Tasks wechseln nach `queued`.
- Lock-Konflikte führen zu Requery, nicht zu partieller Vorbereitung.
- Die Lock-Transaktion enthält keine Git-/Filesystem-Aufrufe.
- `queued_at` und `locked_by` sind für Recovery nachvollziehbar.

## Risiken / Prüfpunkte
- Keine langen DB-Transaktionen.
- Keine all-or-nothing Semantik vortäuschen, wenn die Implementierung partiell aktualisieren kann.
- Keine versteckte Preparation in Repository-Lock-Methoden.

## Modellrouting
`[GPT]` — höchstes Concurrency-Risiko.
