# Arbeitspaket 1-05: Fehlerbehandlung & Retry-Logik

## 1. Titel
**Implementierung robuster Fehlerbehandlung und Retry-Logik für ACP-Kommunikation**

## 2. Ziel
Resiliente Behandlung von transienten Fehlern (Netzwerk, CLI-Timeout, Session-Verlust) mit automatischem Retry und manuellen Fallbacks.

## 3. Fachlicher Kontext / betroffene Domäne
- **Domain**: Error Handling / Resilience
- **Verantwortlichkeit**: Stabilisierung der ACP-Kommunikation bei Fehlern
- **Zielgruppe**: Session-Service, Task-Runner, API

## 4. Betroffene Bestandteile
- **Erweiterung**: `execqueue/workers/opencode_adapter.py`
  - Neue Exceptions: `OpenCodeSessionLostError`, `OpenCodeTimeoutError`
  - Retry-Decorator oder -Wrapper für Client-Methoden
- **Erweiterung**: `execqueue/services/opencode_session_service.py`
  - Integration von Retry-Logik in Service-Methoden
- **Keine neuen Module**: Fehlerbehandlung bleibt im bestehenden Kontext

## 5. Konkrete Umsetzungsschritte
1. **Erweiterte Exceptions definieren** (`opencode_adapter.py`):
   ```python
   class OpenCodeSessionLostError(OpenCodeError):
       """Session wurde vom Server beendet oder ist nicht erreichbar."""
       pass
   
   class OpenCodeTimeoutError(OpenCodeError):
       """CLI-Call oder Session-Timeout."""
       pass
   ```

2. **Retry-Decorator implementieren** (`opencode_adapter.py`):
   - Decorator: `@retry_on_transient_errors(max_retries=3, backoff=2.0)`
   - Triggert bei: `OpenCodeConnectionError`, `OpenCodeTimeoutError`, `OpenCodeSessionLostError`
   - Nicht bei: `OpenCodeHTTPError` (4xx), `OpenCodeConfigurationError`
   - Exponential Backoff: 1s, 2s, 4s, max 10s

3. **Retry-Strategie im Service** (`opencode_session_service.py`):
   - `create_session()`: Max 3 Retries, dann Fail
   - `monitor_sessions()`: 1 Retry, dann markieren als "needs_manual_check"
   - `continue_session()`: Max 2 Retries, dann Wake-up mit anderem Prompt
   
4. **Fallback-Logik**:
   - Wenn Session verloren geht:
     - Option A: Neustart mit `--fork` (neue Session aus checkpoint)
     - Option B: Manuelle Prüfung (Task in "needs_review" Status)
   - Wenn CLI nicht erreichbar:
     - Alert via Logging
     - Task in DLQ verschieben

5. **Circuit Breaker** (optional):
   - Wenn X% der Calls fehlschlagen:
     - Circuit öffnet für Y Sekunden
     - Alle Calls werden sofort abgelehnt
     - Nach Y Sekunden: Half-Open (ein Test-Call)

## 6. Architektur- und Codequalitätsvorgaben
- **DRY**: Retry-Logik als Decorator, nicht duplizieren
- **Configurable**: Max Retries und Backoff aus Environment
- **Logging**: Jeder Retry wird geloggt mit Grund und Attempt-Nummer
- **Testability**: Decorator ist mockbar in Tests

## 7. Abgrenzung: Was nicht Teil des Pakets ist
- **Kein Circuit Breaker Library**: Erst einfache Retry-Logik, später ggf. `tenacity` oder `pybreaker`
- **Kein Alerting**: Keine externe Alerting-Integration (Slack, Email)
- **Kein Auto-Recovery**: Komplexe Recovery-Strategien sind manuell

## 8. Abhängigkeiten
- **Blockiert durch**: AP-1, AP-3
- **Blockiert**: Keine (kann parallel zu AP-6)

## 9. Akzeptanzkriterien
- [ ] Neue Exceptions sind definiert und sinnvoll
- [ ] Retry-Decorator funktioniert (Unit-Test mit Mock)
- [ ] Service nutzt Retry bei transienten Fehlern
- [ ] Fallback-Logik bei Session-Loss ist implementiert
- [ ] Logging zeigt Retry-Versuche klar an
- [ ] Config-Variablen für Max Retries existieren

## 10. Risiken / Prüfpunkte
- **Endless Loops**: Retry bei permanenten Fehlern
  - *Lösung*: Max Retries + Unterscheidung transient/permanent
- **Performance**: Zu viele Retries blockieren Scheduler
  - *Lösung*: Timeout pro Retry + Circuit Breaker (später)

## 11. Begründung für neue Dateien/Module
**Keine neuen Dateien!**  
Die Logik wird in `opencode_adapter.py` und `opencode_session_service.py` integriert, da:
- Retry-Logik eng mit Client/Service verzahnt ist
- Keine allgemeine Wiederverwendung (nur für ACP)
- Bestehende Files bereits Error-Handling enthalten

## 12. Empfohlener Dateiname
`execqueue/workers/opencode_adapter.py` und `execqueue/services/opencode_session_service.py` (erweitert)

## 13. Zielpfad
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/workers/opencode_adapter.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/execqueue/services/opencode_session_service.py`

EXECQUEUE.STATUS.FINISHED
