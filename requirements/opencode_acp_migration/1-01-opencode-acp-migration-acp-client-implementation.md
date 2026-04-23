# Arbeitspaket 1-01: ACP-Client Implementierung

## 1. Titel
**Implementierung des OpenCode ACP-Client (CLI-basiert)**

## 2. Ziel
Erstellung eines robusten CLI-Wrappers, der mit dem OpenCode ACP-Server kommuniziert und Session-Operationen (Start, Status, Continue, Export) ausführt.

## 3. Fachlicher Kontext / betroffene Domäne
- **Domain**: Worker / OpenCode Integration
- **Verantwortlichkeit**: Low-Level Kommunikation mit OpenCode CLI
- **Zielgruppe**: Session-Management Service (siehe AP-2)

## 4. Betroffene Bestandteile
- **Erweiterung**: `execqueue/workers/opencode_adapter.py`
  - Neue Klasse: `OpenCodeACPClient` (innerhalb derselben Datei)
  - Bestehende Klasse `OpenCodeClient` bleibt für REST-Fallback erhalten (optional)
- **Erweiterung**: `execqueue/runtime.py`
  - Neue Funktionen: `get_opencode_acp_url()`, `get_opencode_session_timeout()`
- **Keine neuen Dateien**: Die Logik bleibt in `opencode_adapter.py` gebündelt, da sie nur hier verwendet wird.

## 5. Konkrete Umsetzungsschritte
1. **Konfiguration erweitern** (`runtime.py`):
   - `get_opencode_acp_url()` → Liest `OPENCODE_ACP_URL` (Default: `http://localhost:8765`)
   - `get_opencode_session_timeout()` → Liest `OPENCODE_SESSION_TIMEOUT` (Default: 300)
   - `get_opencode_password()` → Bereits vorhanden, für `--password` nutzen

2. **ACP-Client Klasse erstellen** (`opencode_adapter.py`):
   - Klasse: `OpenCodeACPClient`
   - Methoden:
     - `__init__(self, acp_url: str, password: str | None, timeout: int)`
     - `start_session(self, prompt: str, cwd: str, title: str | None) -> str` (gibt Session-ID zurück)
     - `get_session_status(self, session_id: str) -> dict` (parsed JSON-Output)
     - `continue_session(self, session_id: str, prompt: str | None) -> dict`
     - `export_session(self, session_id: str) -> dict`
     - `close_session(self, session_id: str) -> None`
   - Implementierung via `subprocess.run()` mit `opencode run --attach --format json`
   - JSON-Ausgabe validieren und strukturieren

3. **Fehlerbehandlung**:
   - `subprocess.TimeoutExpired` → Eigene Exception `OpenCodeTimeoutError`
   - `subprocess.CalledProcessError` → `OpenCodeConnectionError` mit stdout/stderr
   - JSON-Parsing-Fehler → `OpenCodeHTTPError` mit Status "parse_error"

4. **Logging**:
   - Info: "ACP Session started: id=X, cwd=Y"
   - Warning: "ACP Session timeout after Z seconds"
   - Error: "ACP CLI error: {stderr}"

## 6. Architektur- und Codequalitätsvorgaben
- **Minimal Invasivität**: Keine neuen Module, alles in `opencode_adapter.py`
- **Type Hints**: Alle Funktionen müssen getypt sein
- **Docstrings**: Google-Style für öffentliche Methoden
- **Testing**: Unit-Tests mit `subprocess`-Mocking (siehe AP-6)
- **Keine premature Optimization**: Erst CLI, später ggf. WebSocket

## 7. Abgrenzung: Was nicht Teil des Pakets ist
- **Kein WebSocket-Client**: Erst CLI, Performance-Optimierung später
- **Kein Session-Pooling**: Einzelne Sessions, kein Connection-Pool
- **Keine UI-Integration**: Nur Backend-Logik
- **Keine REST-Fallback-Logik**: REST-Adapter bleibt unverändert (kann später deprecated werden)

## 8. Abhängigkeiten
- **Blockiert durch**: Keine (kann parallel zu AP-2 begonnen werden)
- **Blockiert**: AP-2 (Session-Management Service benötigt diesen Client)

## 9. Akzeptanzkriterien
- [ ] `OpenCodeACPClient` Klasse existiert in `opencode_adapter.py`
- [ ] Alle 5 Methoden sind implementiert und getypt
- [ ] `subprocess`-Aufrufe sind robust (Timeout, Error-Handling)
- [ ] JSON-Output wird validiert und in `OpenCodeExecutionResult` übersetzt
- [ ] Logging ist konsistent mit bestehendem Stil
- [ ] Unit-Tests bestehen (siehe AP-6)

## 10. Risiken / Prüfpunkte
- **CLI-Änderungen**: OpenCode-CLI kann sich ändern → Strikte JSON-Validierung
- **Path-Issues**: `opencode` Binary muss im `PATH` sein → Check bei Initialisierung
- **Encoding**: stdout/stderr muss als UTF-8 decodiert werden

## 11. Begründung für neue Dateien/Module
**Keine neuen Dateien!**  
Die Logik wird in `execqueue/workers/opencode_adapter.py` integriert, da:
- Der Client nur von diesem Modul verwendet wird
- Bestehende Exceptions und Result-Klassen wiederverwendet werden
- Die Datei bereits ~350 Zeilen hat, aber durch Zusammenfassung übersichtlich bleibt

## 12. Empfohlener Dateiname
`execqueue/workers/opencode_adapter.py` (erweitert)

## 13. Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/workers/opencode_adapter.py`

EXECQUEUE.STATUS.FINISHED
