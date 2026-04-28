# 07 — Preparation Failure Handling and Stale Queued Recovery

## Ziel
Fehler während der Preparation strukturiert behandeln und Tasks erkennen, die zu lange in `queued` verbleiben.

## Aufwand
Ca. 2h

## Scope
Enthalten:
- Fehlerklassifikation.
- Retry-/Attempt-Handling.
- Stale-Queued-Recovery.
- Recovery-Matrix nach Side-Effect-State.

Nicht enthalten:
- Runner-Watchdog.
- Recovery für `in_progress`.
- Merge-/Review-Recovery.

## Recovery-Matrix
| Zustand | Beispiel | Zielstatus | Bedingung |
|---|---|---:|---|
| Recoverable ohne Side Effects | temporärer DB-/Config-/Git-Read-Fehler vor Worktree-Erzeugung | `backlog` | attempt < max |
| Recoverable mit task-owned Side Effects | Worktree teilweise erzeugt, eindeutig task-owned | `backlog` oder `failed` | nur nach safe cleanup oder expliziter Dokumentation |
| Conflict | Branch/Worktree von anderem Task belegt | `backlog` oder `failed` | abhängig von Retry-Policy |
| Non-recoverable | invalider Pfad, ungültige Branch, Security Guard verletzt | `failed` | sofort |
| Retry exhausted | wiederholte recoverable Fehler | `failed` | attempt >= max |
| `in_progress` | Runner läuft oder lief an | keine Änderung | außerhalb REQ-011 |

## Technical Specification
- Fehlerklassen:
  - `recoverable`
  - `conflict`
  - `non_recoverable`
- Felder aktualisieren:
  - `preparation_attempt_count += 1`
  - `last_preparation_error`
  - `updated_at`
  - optional `last_recovery_at`
- Stale Query:
  - `status = queued`
  - `queued_at < now - timeout`
  - `locked_by` optional berücksichtigen
- Recovery darf ausschließlich `queued`-Tasks anfassen.

## Umsetzungsschritte
1. Timeout- und Retry-Konfiguration definieren.
2. Preparation-Fehler typed modellieren.
3. Statusübergänge für Fehlerfälle implementieren.
4. Stale-Queued-Query implementieren.
5. Side-Effect-State für Branch/Worktree dokumentieren oder speichern.
6. Recovery-Tests für Grenzfälle ergänzen.

## Akzeptanzkriterien
- Preparation-Fehler lassen Tasks nicht dauerhaft in `queued` hängen.
- Recoverable, conflict und non-recoverable Fehler werden unterschiedlich behandelt.
- Retry-Limit verhindert Endlosschleifen.
- Stale queued Tasks werden über Timeout erkannt.
- `in_progress` Tasks werden durch diesen Recovery-Flow nie verändert.

## Risiken / Prüfpunkte
- Rücksetzung nach `backlog` nur, wenn keine unsafe Side Effects bestehen.
- Worktree-/Branch-Artefakte nicht blind löschen.
- Recovery nicht als Ersatz für Runner-/Session-Monitoring missverstehen.

## Modellrouting
`[GPT]` — komplexe Fehler-/Recovery-Semantik.
