# Arbeitspaket 1-04: Task-Runner Integration

## 1. Titel
**Integration von OpenCode Session-Management in den Task-Runner**

## 2. Ziel
Automatisches Starten, Monitoring und Abschließen von OpenCode-Sessions als Teil des bestehenden Task-Runner-Workflows.

## 3. Fachlicher Kontext / betroffene Domäne
- **Domain**: Task Execution / Orchestrierung
- **Verantwortlichkeit**: Einbettung von OpenCode in den Lebenszyklus von Tasks
- **Zielgruppe**: Scheduler, Background Worker

## 4. Betroffene Bestandteile
- **Erweiterung**: `execqueue/scheduler/runner.py`
  - Integration von `OpenCodeSessionService` in den Task-Execution-Loop
- **Erweiterung**: `execqueue/api/tasks.py`
  - Optional: Endpoint zum manuellen Trigger von `wake_up_session`
- **Keine neuen Modelle**: Bestehende Task-Modelle reichen aus

## 5. Konkrete Umsetzungsschritte
1. **Scheduler-Integration** (`runner.py`):
   - Inject `OpenCodeSessionService` in Scheduler
   - Im `process_tasks()`-Loop:
     - **Vor Execution**: Prüfen ob Task `opencode_session_id` hat
       - Falls nein: `service.create_session(task)` aufrufen
     - **Während Execution**: `service.monitor_sessions()` aufrufen
     - **Nach Execution**: `service.complete_session(task)` oder `fail_session(task)`
   
2. **Wake-up Mechanismus**:
   - Wenn Task `status=WAITING` (z.B. OpenCode wartet auf Bestätigung):
     - `service.wake_up_session(task, prompt="Fahre fort")`
   - Timeout-Check: Wenn `last_ping < now() - timeout`:
     - Automatisches Wake-up oder Fail (konfigurierbar)

3. **Error Handling**:
   - Falls ACP-Client fehlschlägt:
     - Task in DLQ (Dead Letter Queue) verschieben
     - Alert/Log für manuelle Prüfung
   - Retry-Logik: Max 3 Retries mit Exponential Backoff

4. **Logging & Monitoring**:
   - Session-ID in allen Task-Logs
   - Metrics: `opencode_sessions_active`, `opencode_sessions_completed`

## 6. Architektur- und Codequalitätsvorgaben
- **Minimal Invasivität**: Bestehenden Scheduler-Loop erweitern, nicht ersetzen
- **Error Handling**: Alle Exceptions werden abgefangen und in DLQ geloggt
- **Async/Await**: Scheduler ist async, Service muss async sein (oder sync in ThreadPool)
- **Testbarkeit**: Mock `OpenCodeSessionService` in Tests

## 7. Abgrenzung: Was nicht Teil des Pakets ist
- **Keine UI-Integration**: Keine WebSocket-Streams an Frontend
- **Kein neuer Scheduler**: Nutzung des bestehenden Schedulers
- **Keine manuelle Trigger-API**: Kann später kommen (nicht jetzt)

## 8. Abhängigkeiten
- **Blockiert durch**: AP-1, AP-2, AP-3
- **Blockiert**: AP-5 (Error Handling & Retry)

## 9. Akzeptanzkriterien
- [ ] Scheduler startet automatisch Sessions für Tasks mit `opencode_*` Feldern
- [ ] Monitoring läuft im Hintergrund (alle X Sekunden)
- [ ] Wake-up wird automatisch bei Timeout getriggert
- [ ] Fehlerhafte Sessions landen in DLQ
- [ ] Bestehende Tests passen an (Mock Service)
- [ ] E2E-Test mit echtem ACP-Server (siehe AP-6)

## 10. Risiken / Prüfpunkte
- **Scheduler-Overhead**: Zu häufiges Monitoring kann CPU belasten
  - *Lösung*: Config `SCHEDULER_OPENCODE_MONITOR_INTERVAL` (Default: 30s)
- **Session-Leaks**: Beendete Sessions werden nicht gelöscht
  - *Lösung*: `cleanup_expired_sessions()` im Scheduler (später)

## 11. Begründung für neue Dateien/Module
**Keine neuen Dateien!**  
Die Logik wird in `execqueue/scheduler/runner.py` integriert, da:
- Es sich um eine Erweiterung des bestehenden Loops handelt
- Keine neue Domäne entsteht (nur Integration)
- Die Datei bereits ~200 Zeilen hat, aber durch Integration übersichtlich bleibt

## 12. Empfohlener Dateiname
`execqueue/scheduler/runner.py` (erweitert)

## 13. Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/scheduler/runner.py`

EXECQUEUE.STATUS.FINISHED
