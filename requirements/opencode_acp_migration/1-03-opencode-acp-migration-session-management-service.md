# Arbeitspaket 1-03: Session-Management Service

## 1. Titel
**Implementierung des OpenCode Session-Management Services**

## 2. Ziel
Zentraler Service für Session-Lebenszyklus: Start, Monitoring, Wake-up, Export und Cleanup.

## 3. Fachlicher Kontext / betroffene Domäne
- **Domain**: Business Logic / Orchestrierung
- **Verantwortlichkeit**: Koordination von OpenCode-Sessions über Tasks hinweg
- **Zielgruppe**: Task-Runner, API-Endpoints, Scheduler

## 4. Betroffene Bestandteile
- **Neue Datei**: `execqueue/services/opencode_session_service.py`
  - **Begründung**: Diese Logik ist fachlich eigenständig und wird von mehreren Stellen genutzt (Scheduler, API, CLI). Eine separate Service-Datei ist gerechtfertigt.
- **Erweiterung**: `execqueue/workers/opencode_adapter.py`
  - Nutzung von `OpenCodeACPClient` (aus AP-1)
- **Erweiterung**: `execqueue/runtime.py`
  - `get_opencode_max_parallel_sessions()` (optional)

## 5. Konkrete Umsetzungsschritte
1. **Service-Klasse erstellen** (`opencode_session_service.py`):
   - Klasse: `OpenCodeSessionService`
   - Constructor: Inject `OpenCodeACPClient` und `Session`-Repository (SQLModel)

2. **Methoden implementieren**:
   - `create_session(task: Task) -> Task`
     - Startet neue ACP-Session via Client
     - Speichert `session_id`, `project_path`, `status=RUNNING` in DB
     - Gibt aktualisiertes Task zurück
   
   - `monitor_sessions() -> list[Task]`
     - Lädt alle Tasks mit `status=RUNNING` oder `WAITING`
     - Prüft Status via ACP-Client
     - Aktualisiert `status` und `last_ping` in DB
     - Gibt geänderte Tasks zurück
   
   - `wake_up_session(task: Task, prompt: str | None) -> Task`
     - Ruft `continue_session()` beim Client auf
     - Setzt `status=RUNNING`, `last_ping=now()`
   
   - `complete_session(task: Task) -> Task`
     - Ruft `export_session()` auf
     - Speichert Ergebnis in `task.result` oder `task.output`
     - Setzt `status=COMPLETED`
   
   - `fail_session(task: Task, error: str) -> Task`
     - Setzt `status=FAILED`, speichert Error-Message
   
   - `cleanup_expired_sessions() -> int`
     - Findet Sessions mit `last_ping < now() - timeout`
     - Beendet sie gracefully oder markiert als FAILED
     - Gibt Anzahl gelöschter Sessions zurück

3. **Timeout-Logik**:
   - Liest `OPENCODE_SESSION_TIMEOUT` aus Config
   - Prüft bei jedem `monitor_sessions()`-Call
   - Trigger `wake_up_session()` oder `fail_session()` bei Timeout

4. **Parallelitäts-Limit**:
   - Optional: Max X Sessions gleichzeitig (Config: `OPENCODE_MAX_PARALLEL`)
   - Verhindert Überlastung des ACP-Servers

## 6. Architektur- und Codequalitätsvorgaben
- **Service-Layer Pattern**: Keine DB-Queries direkt im Service, über Repository
- **Dependency Injection**: Client und DB werden injiziert (testbar)
- **Error Handling**: Alle Exceptions werden in `OpenCodeError` abgefangen
- **Logging**: Strukturierte Logs pro Session-ID
- **Keine Business Logic in API**: Service bleibt unabhängig von FastAPI

## 7. Abgrenzung: Was nicht Teil des Pakets ist
- **Kein Scheduler**: Zeitgesteuertes Monitoring ist Teil des bestehenden Schedulers (nur Integration)
- **Keine UI**: Keine WebSocket-Streaming-Logik
- **Kein Retry-Mechanismus**: Retry-Logik ist Teil von AP-4 (Task-Runner)

## 8. Abhängigkeiten
- **Blockiert durch**: AP-1 (ACP-Client), AP-2 (DB-Schema)
- **Blockiert**: AP-4 (Task-Runner Integration)

## 9. Akzeptanzkriterien
- [ ] `OpenCodeSessionService` Klasse existiert und ist injizierbar
- [ ] Alle 6 Methoden sind implementiert und getypt
- [ ] DB-Operationen nutzen SQLModel-Queries
- [ ] Timeout-Logik funktioniert korrekt
- [ ] Parallelitäts-Limit wird respektiert (falls konfiguriert)
- [ ] Unit-Tests bestehen

## 10. Risiken / Prüfpunkte
- **Race Conditions**: Zwei Scheduler-Instanzen könnten gleiche Session monitorn
  - *Lösung*: `instance_id` oder DB-Locking (später)
- **Memory Leaks**: Lange Sessions können viel Log-Daten sammeln
  - *Lösung*: Limit auf X MB pro Session (später)

## 11. Begründung für neue Dateien/Module
**Neue Datei: `execqueue/services/opencode_session_service.py`**
- **Begründung**: 
  - Die Session-Logik ist fachlich eigenständig (Lifecycle-Management)
  - Wird von mehreren Stellen genutzt (Scheduler, API, CLI)
  - Bestehende `services/`-Dateien (z.B. `task_service.py`) wären zu groß
  - Klare fachliche Grenze: "Session Orchestrierung" vs. "Task CRUD"

## 12. Empfohlener Dateiname
`execqueue/services/opencode_session_service.py`

## 13. Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/services/opencode_session_service.py`

EXECQUEUE.STATUS.FINISHED
