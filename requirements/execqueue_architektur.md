# ExecQueue -- Architektur & Roadmap

## TL;DR

ExecQueue orchestriert Anforderungen als Tasks, führt sie über OpenCode
aus und wiederholt die Ausführung so lange, bis ein verifiziertes
Ergebnis erreicht ist.

------------------------------------------------------------------------

## 1. Ziel des Systems

Task = (Artifact + Prompt) → Execution → Validation → Retry → DONE

------------------------------------------------------------------------

## 2. Systemarchitektur

User (Telegram / OpenClaw) → ExecQueue API (FastAPI) → Database
(Postgres) → Scheduler / Runner → OpenCode (Execution Engine)

------------------------------------------------------------------------

## 3. Datenmodell

### Requirement (Epic)

-   title
-   description
-   markdown_content
-   status
-   verification_prompt

### WorkPackage

-   requirement_id
-   title
-   description
-   execution_order
-   implementation_prompt
-   verification_prompt
-   status

### Task

-   source_type (requirement \| work_package)
-   source_id
-   prompt
-   verification_prompt
-   status
-   retry_count
-   max_retries

------------------------------------------------------------------------

## 4. Queue-Regel

IF Requirement hat WorkPackages: → WorkPackages als Tasks ELSE: →
Requirement selbst als Task

------------------------------------------------------------------------

## 5. Task Lifecycle

queued → in_progress → validation → done \| retry \| failed

------------------------------------------------------------------------

## 6. Execution Flow

1.  Task holen
2.  OpenCode ausführen
3.  Ergebnis validieren
4.  DONE oder RETRY

------------------------------------------------------------------------

## 7. Validation

Output muss JSON sein: { "status": "done" \| "not_done", "summary":
"...", "evidence": "..." }

------------------------------------------------------------------------

## 8. Aktueller Stand

-   FastAPI
-   Postgres
-   Requirement / WorkPackage / Task
-   Queue + Runner
-   Validation (basic)
-   OpenCode Stub

------------------------------------------------------------------------

## 9. Offene Punkte

-   Scheduler Loop
-   OpenCode Integration
-   Validation härten
-   Retry verbessern
-   Background Worker
-   Telegram Integration

------------------------------------------------------------------------

## 10. Nächste Schritte

1.  Scheduler Loop
2.  Background Worker
3.  OpenCode Adapter
4.  Validation verbessern
5.  Telegram Commands

------------------------------------------------------------------------

## 11. Design-Regeln

-   Alles ist ein Task
-   Validation entscheidet
-   Kein unendlicher Loop
-   JSON Output Pflicht

------------------------------------------------------------------------

## 12. Zielzustand

Autonomes System zur Abarbeitung von Anforderungen mit Retry-Logik und
Remote-Steuerung.
