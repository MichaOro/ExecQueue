# Arbeitspaket 1-06: End-to-End Test & Validierung

## 1. Titel
**End-to-End Test der ACP-Integration mit echtem OpenCode-Server**

## 2. Ziel
Validierung der gesamten ACP-Migration durch Integrationstests mit einem laufenden ACP-Server und realen Projekt-Contexts.

## 3. Fachlicher Kontext / betroffene Domäne
- **Domain**: Testing / Quality Assurance
- **Verantwortlichkeit**: Sicherstellen, dass alle Komponenten zusammenarbeiten
- **Zielgruppe**: Entwickler, CI/CD Pipeline

## 4. Betroffene Bestandteile
- **Neue Datei**: `tests/integration/test_opencode_acp_integration.py`
  - **Begründung**: Integrationstests benötigen eigenen Kontext und setzen ACP-Server voraus. Separater Test-File ist gerechtfertigt.
- **Erweiterung**: `tests/conftest.py`
  - Fixtures für ACP-Server (Start/Stop)
  - Fixtures für Test-Projects (temporäre Verzeichnisse)
- **Erweiterung**: `tests/unit/test_opencode_adapter.py`
  - Anpassung der Tests für ACP-Client (nicht REST)

## 5. Konkrete Umsetzungsschritte
1. **Test-Setup** (`conftest.py`):
   - Fixture: `acp_server`
     - Startet `opencode acp --port 8766` (Test-Port)
     - Wartet auf Ready (Health-Check)
     - Stoppt nach Test
   
   - Fixture: `test_project_dir`
     - Erstellt temporäres Verzeichnis mit minimalem Projekt
     - Bereinigt nach Test

2. **Integrationstests** (`test_opencode_acp_integration.py`):
   
   **Test 1: Session erstellen und beenden**
   ```python
   def test_create_and_complete_session(acp_server, test_project_dir):
       client = OpenCodeACPClient(acp_url="http://localhost:8766", password="test")
       session_id = client.start_session("echo 'Hello'", cwd=test_project_dir)
       assert session_id is not None
       
       status = client.get_session_status(session_id)
       assert status["status"] == "running"
       
       result = client.export_session(session_id)
       assert "Hello" in result["output"]
   ```
   
   **Test 2: Session fortsetzen (Wake-up)**
   ```python
   def test_continue_session(acp_server, test_project_dir):
       # Session starten, dann pausieren
       # Wake-up mit "Fahre fort"
       # Ergebnis prüfen
   ```
   
   **Test 3: Timeout-Handling**
   ```python
   def test_session_timeout(acp_server, test_project_dir):
       # Session starten
       # last_ping nicht aktualisieren
       # Timeout-Check sollte Session als FAILED markieren
   ```
   
   **Test 4: Fehlerbehandlung**
   ```python
   def test_invalid_prompt_error(acp_server, test_project_dir):
       # Ungültigen Prompt senden
       # Prüfen ob OpenCodeHTTPError geworfen wird
   ```

3. **Service-Integrationstests**:
   - Test `OpenCodeSessionService` mit echtem ACP-Server
   - Test `monitor_sessions()` Loop
   - Test `cleanup_expired_sessions()`

4. **End-to-End Workflow** (optional, langsam):
   - Task in DB erstellen
   - Scheduler startet automatisch Session
   - Session läuft zu Ende
   - Task hat `status=COMPLETED` und Ergebnis

5. **Performance-Test** (optional):
   - 5 parallele Sessions gleichzeitig
   - Prüfen ob Memory/CPU im Rahmen bleibt

## 6. Architektur- und Codequalitätsvorgaben
- **Isolation**: Jeder Test startet eigenen ACP-Server (Port 8766-X)
- **Cleanup**: Temporäre Dateien werden nach Test gelöscht
- **Timeout**: Tests haben Max-Timeout (z.B. 60s pro Session)
- **Parallel**: Tests können parallel laufen (verschiedene Ports)

## 7. Abgrenzung: Was nicht Teil des Pakets ist
- **Keine Load-Tests**: Kein Stress-Test mit 100 Sessions
- **Keine UI-Tests**: Keine Selenium/Playwright Tests
- **Kein CI/CD-Setup**: Tests sind manuell ausführbar, CI-Integration später

## 8. Abhängigkeiten
- **Blockiert durch**: AP-1, AP-2, AP-3, AP-4, AP-5
- **Blockiert**: Keine (finaler Validierungsschritt)

## 9. Akzeptanzkriterien
- [ ] Alle 4 Integrationstests bestehen
- [ ] Service-Integrationstests bestehen
- [ ] E2E-Workflow funktioniert (optional)
- [ ] Tests sind isoliert (kein State zwischen Tests)
- [ ] Cleanup funktioniert (keine temporären Files übrig)
- [ ] Tests laufen in < 5 Minuten gesamt

## 10. Risiken / Prüfpunkte
- **ACP-Server startet nicht**: Timeout im Fixture
  - *Lösung*: Health-Check mit Retry (max 10s)
- **Tests sind zu langsam**: Session-Execution dauert lange
  - *Lösung*: Kurze Prompts verwenden, Timeout auf 30s begrenzen
- **Port-Konflikte**: Test-Port ist belegt
  - *Lösung*: Dynamische Port-Allokation (`--port 0`)

## 11. Begründung für neue Dateien/Module
**Neue Datei: `tests/integration/test_opencode_acp_integration.py`**
- **Begründung**:
  - Integrationstests sind fachlich von Unit-Tests getrennt
  - Benötigen eigenes Setup (ACP-Server)
  - Bestehende `test_opencode_adapter.py` ist reine Unit-Test-Datei
  - Klare Trennung: Unit (Mock) vs. Integration (Real)

## 12. Empfohlener Dateiname
`tests/integration/test_opencode_acp_integration.py`

## 13. Zielpfad
`/home/ubuntu/workspace/IdeaProjects/ExecQueue/tests/integration/test_opencode_acp_integration.py`

EXECQUEUE.STATUS.FINISHED
