# 02 — Trigger and Executable Candidate Discovery

## Ziel
Den Orchestrator nach Task-Persistenz idempotent aktivieren und ausführbare `backlog`-Tasks deterministisch aus der DB laden.

## Aufwand
Ca. 2h

## Scope
Enthalten:
- Trigger als Wake-up-Signal.
- DB als Source of Truth.
- Candidate Query für ausführbare Tasks.
- Deterministische Sortierung und `max_batch_size`.

Nicht enthalten:
- Locking.
- Batch Planning.
- Git-/Runner-Kontext.

## Fachliche Regeln
- Der Trigger enthält keine authoritative Task-Liste.
- Der Trigger darf mehrfach eintreffen, ohne doppelte Ausführung zu verursachen.
- Trigger-Fehler dürfen Task-Erzeugung nicht rollbacken.
- Candidate Discovery lädt nur `status = backlog`.
- Dependencies, Blocking Conditions und Requirement-Zustände werden konservativ ausgewertet.

## Technical Specification
- Trigger-Aufruf erst nach erfolgreichem Task-Persist/Commit.
- Trigger-Fehler: strukturiert loggen, Task-Persistenz nicht rückgängig machen.
- Candidate Query:
  - `status = backlog`
  - unterstützte `task_type`: `planning`, `analysis`, `execution`; `requirement` nur, wenn im System als ausführbarer Container vorgesehen
  - erfüllte Dependencies
  - nicht gesperrt/blockiert
  - stabile Sortierung: `priority DESC`, `order_index ASC`, `created_at ASC`, `task_id ASC`
  - `max_batch_size`

## Umsetzungsschritte
1. Task-Erzeugungsfluss und Commit-Grenze verifizieren.
2. Trigger nach Commit platzieren oder bestehende Platzierung korrigieren.
3. Trigger idempotent und side-effect-arm halten.
4. Candidate Query über Repository/Service-Schicht implementieren.
5. Dependency-/Blocking-Filter konservativ anbinden.
6. Query- und Trigger-Tests ergänzen.

## Akzeptanzkriterien
- Persistierte Tasks lösen einen Trigger aus.
- Trigger-Fehler rollt persistierte Tasks nicht zurück.
- Orchestrator lädt Tasks aus der DB, nicht aus dem Trigger-Payload.
- Query liefert nur ausführbare `backlog`-Tasks.
- Sortierung ist wiederholbar und testbar.

## Risiken / Prüfpunkte
- `requirement` darf nicht fälschlich als direkt ausführbarer Task behandelt werden.
- Keine implizite Ausführung im Trigger implementieren.
- Kein Locking in diesem Paket verstecken.

## Modellrouting
`[QWN]` — klare Query-/Service-Logik, geringe Concurrency-Komplexität.
