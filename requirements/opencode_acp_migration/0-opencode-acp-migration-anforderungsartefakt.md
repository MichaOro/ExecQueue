# Anforderungsartefakt: Migration zu OpenCode ACP (Agent Client Protocol)

## 1. Titel
**Migration des OpenCode Adapters von REST zu ACP (Agent Client Protocol)**

## 2. Kurzbeschreibung
Umsstellung der Kommunikation zwischen ExecQueue und OpenCode von einem hypothetischen REST-Endpoint hin zum offiziellen **Agent Client Protocol (ACP)**. Dies ermöglicht projekt-spezifische, session-basierte Orchestrierung paralleler AI-Entwicklungsaufgaben über mehrere Repositorys hinweg.

## 3. Zielbild / gewünschter Endzustand
- ExecQueue kann **parallele AI-Sessions** in verschiedenen Projekt-Verzeichnissen steuern.
- Jede Aufgabe (Requirement/Task) ist einer **persisten OpenCode Session** zugeordnet.
- Der Adapter nutzt `opencode acp` als Backend und `opencode run --attach` für die Steuerung.
- Status-Monitoring, "Wake-up"-Pings und Ergebnis-Exporte sind über Session-IDs möglich.
- Keine Abhängigkeit von nicht-existierenden REST-Endpoints (`/execute`).

## 4. Ausgangslage / Problem
- **Aktueller Status**: Der `OpenCodeAdapter` erwartet einen REST-Endpoint (`POST /execute`), der vom OpenCode-Server (Port 4096) nicht bereitgestellt wird. Der Server liefert stattdessen HTML (Web-UI).
- **Problem**: Die geplante Orchestrierung ("In Projekt X mache A, in Projekt Y mache B") ist mit dem aktuellen Ansatz nicht möglich.
- **Erkenntnis**: OpenCode stellt die Schnittstelle für externe Steuerung über **ACP** und **CLI-Commands** bereit, nicht über eine einfache REST API.

## 5. Fachlicher Kontext
ExecQueue soll als **Orchestrator** fungieren, der:
1. Anforderungen in Arbeitspakete zerlegt.
2. Diese Pakete an OpenCode delegiert, wobei jedes Paket in einem **spezifischen Projekt-Context** (Verzeichnis) ausgeführt wird.
3. Den Fortschritt überwacht und bei Stillstand (z.B. Warten auf Bestätigung) "Wake-up"-Signale sendet.
4. Ergebnisse automatisch integriert oder zur Prüfung markiert.

## 6. Technischer Kontext
- **Backend**: OpenCode CLI (`opencode` Binary) mit `acp` Subcommand.
- **Kommunikation**: CLI-basierte Steuerung (`--attach`, `--session`, `--format json`) oder WebSocket-Verbindung zum ACP-Server.
- **Datenhaltung**: Session-IDs und Projekt-Pfade müssen im ExecQueue-Modell (`Task`, `WorkPackage`) persistiert werden.
- **Konfiguration**: `OPENCODE_ACP_URL` (z.B. `http://localhost:8765`) statt `OPENCODE_BASE_URL`.

## 7. Relevante bestehende Bestandteile
- `execqueue/workers/opencode_adapter.py`: Aktueller REST-basierter Adapter (muss refaktoriert werden).
- `execqueue/runtime.py`: Konfigurations-Lese-Funktionen (muss um ACP-URL erweitert werden).
- `execqueue/models/task.py`: Task-Modell (muss `session_id` und `project_path` aufnehmen).
- `tests/unit/test_opencode_adapter.py`: Bestehende Tests (müssen an neue Architektur angepasst werden).

## 8. Anforderungen

### 8.1 Muss-Anforderungen
- **ACP-Client**: Implementierung eines Clients, der mit einem laufenden ACP-Server kommuniziert.
- **Session-Management**: Fähigkeit, neue Sessions mit Projekt-Context (`--cwd`) zu starten und Session-IDs zu speichern.
- **JSON-Output**: Parsing von `opencode run --format json` Events zur Status-Erfassung.
- **Monitoring**: Abfrage des Session-Status (z.B. `opencode session list` oder ACP-Status-Endpoint).
- **Wake-up Mechanismus**: Fortsetzung einer Session via `--continue` bei Stillstand.
- **Ergebnis-Export**: Extrahierung des finalen Outputs einer Session (`opencode export`).
- **Fehlerbehandlung**: Robustes Handling von CLI-Fehlern, Timeouts und Verbindungsabbrüchen.

### 8.2 Soll-Anforderungen
- **Parallelität**: Unterstützung mehrerer gleichzeitiger Sessions pro Projekt.
- **Logging**: Strukturierte Protokollierung von OpenCode-Events (Thinking, Actions, Results).
- **Konfiguration**: Umgebungsvariable `OPENCODE_ACP_URL` und `OPENCODE_SESSION_TIMEOUT`.
- **Cleanup**: Automatisches Beenden von Sessions nach Abschluss oder Timeout.

### 8.3 Kann-Anforderungen
- **WebSocket-Integration**: Direkte WebSocket-Kommunikation statt CLI-Subprocess (Performance).
- **Event-Stream**: Echtzeit-Streaming von "Thinking"-Phasen an die UI.
- **Checkpointing**: Manuelle Sicherung von Session-Zuständen.

## 9. Nicht-Ziele / Abgrenzung
- **Keine REST-Implementierung**: Es wird kein eigener REST-Server für OpenCode gebaut.
- **Keine UI-Änderungen**: Die Web-UI von OpenCode wird nicht verändert.
- **Kein Model-Training**: Keine Änderungen an den AI-Modellen selbst.
- **Keine Alembic-Migrationen**: Schema-Änderungen manuell via `SQLModel.metadata.create_all()`.

## 10. Randbedingungen / Constraints
- **CLI-Abhängigkeit**: `opencode` Binary muss im `PATH` verfügbar sein.
- **Port-Konflikt**: ACP-Server muss auf einem freien Port laufen (Default: 8765).
- **Session-Limits**: Begrenzung der parallelen Sessions pro Projekt (Konfigurierbar).
- **Timeout**: Sessions müssen nach definierter Zeit (z.B. 300s) automatisch "aufgeweckt" oder beendet werden.

## 11. Architektur- und Strukturvorgaben
- **Minimal Invasivität**: Bestehende `OpenCodeClient`-Struktur beibehalten, aber Implementierung anpassen.
- **Service-Layer**: Neue `OpenCodeACPService` Klasse für Session-Logik.
- **Adapter-Pattern**: `OpenCodeAdapter` bleibt die Schnittstelle zu ExecQueue, intern nutzt er den ACP-Client.
- **Keine neuen Module** wenn bestehende erweitert werden können (z.B. `runtime.py` erweitern).

## 12. Daten / Schnittstellen / Abhängigkeiten
- **Eingabe**: Prompt, Projekt-Pfad (`cwd`), Session-ID (optional).
- **Ausgabe**: JSON-Events (Status, Output, Errors), Session-ID.
- **Abhängigkeiten**: `subprocess` (für CLI), `httpx` (falls WebSocket/HTTP genutzt wird), `json`.
- **Datenbank**: Neue Felder in `Task`/`WorkPackage`:
  - `opencode_session_id` (String, nullable)
  - `opencode_project_path` (String, nullable)
  - `opencode_status` (Enum: pending, running, waiting, completed, failed)

## 13. Risiken / technische Prüfpunkte
- **CLI-Stabilität**: Parsing von CLI-Ausgaben kann bei Änderungen der OpenCode-CLI brechen.
  - *Lösung*: Strikte Nutzung von `--format json` und Schema-Validierung.
- **Session-Persistenz**: Sessions können verloren gehen bei Server-Neustart.
  - *Lösung*: Session-IDs persistieren und `--continue` nutzen.
- **Performance**: CLI-Subprocess-Overhead bei häufigen Calls.
  - *Lösung*: Connection-Pooling oder direkte ACP-Protokoll-Implementierung prüfen.
- **Authentifizierung**: ACP-Server benötigt ggf. Password-Auth (`--password`).

## 14. Offene Fragen / Klärungsbedarf
- **ACP-Protokoll-Spezifikation**: Gibt es eine offizielle Dokumentation für das ACP-Protokoll (WebSocket vs. HTTP)?
- **Session-Lifecycle**: Wie lange bleiben Sessions aktiv? Gibt es eine TTL?
- **Error-Codes**: Welche JSON-Error-Codes sendet OpenCode bei Fehlern?
- **Parallelität**: Wie viele Sessions pro Projekt sind sinnvoll/unterstützt?

## 15. Vorschlag für spätere Arbeitspakete
- **AP-1**: ACP-Client Implementierung (CLI-Wrapper oder WebSocket-Client).
- **AP-2**: Datenbank-Schema-Erweiterung (Session-ID, Status, Pfad).
- **AP-3**: Session-Management Service (Start, Monitor, Continue, Export).
- **AP-4**: Integration in Task-Runner (Automatisches Starten/Monitoring).
- **AP-5**: Fehlerbehandlung & Retry-Logik für ACP-Kommunikation.
- **AP-6**: End-to-End Test mit echtem OpenCode-Server und Projekt-Context.

## 16. Akzeptanzkriterien auf Artefakt-Ebene
- [ ] Anforderung ist technisch präzise und für eine Implementierung nutzbar.
- [ ] Risiken und offene Fragen sind explizit benannt.
- [ ] Abgrenzung zu REST-Ansatz ist klar.
- [ ] Vorschlag für Arbeitspakete ist logisch und umsetzbar.
- [ ] Bestehende Projekt-Patterns (Minimal Invasivität) werden berücksichtigt.

## 17. Ablagehinweis
- **Pfad**: `/home/ubuntu/workspace/IdeaProjects/ExecQueue_requirements/opencode_acp_migration/`
- **Dateiname**: `0-opencode-acp-migration-anforderungsartefakt.md`

EXECQUEUE.STATUS.FINISHED
