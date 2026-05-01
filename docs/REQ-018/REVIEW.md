**REVIEW.md**

# Review von REQ‑018 (Error Handling & Retry Mechanism)

## 1. Zusammenfassung der Anforderungen
Der Anforderungssatz REQ‑018 beschreibt sechs Arbeitspakete (AP‑01 … AP‑06), die darauf abzielen, ein robustes Fehlerbehandlungs- und Wiederholungsmechanismus zum ExecQueue-System hinzuzufügen. Die Kernideen sind:

1. **Fehlerklassifizierung** – definiere eine Taxonomie von Fehlertypen (transient vs. permanent) und ordne ihnen die Wiederholungsberechtigung zu.  
2. **Wiederholungsmechanismus** – implementiere exponentielles Back-off mit Jitter, wobei die pro‑Aufgabe `max_retries` beachtet wird.  
3. **Erkennung und Wiederherstellung veralteter Ausführungen** – erkenne Aufgaben, die innerhalb eines Timeouts nicht vorangeschritten sind, und wiederhole sie oder breche sie ab.  
4. **Workflow-Abbruch & Orchestrator-Benachrichtigung** – verbreite Abbruchsignale an den Orchestrator, damit er abhängige Workflows abbrechen kann.  
5. **Fehlerpersistenz & Observabilität** – speichere Fehlerdetails in einem dauerhaften Speicher und stelle sie über Metriken/Tracing bereit.  
- **API-Endpunkte** (optional) – stelle Endpunkte bereit, um Fehlerstatistiken abzufragen, manuelle Wiederholungen auszulösen und Fehlerverläufe abzurufen.

## 2. Stärken der aktuellen Spezifikation
- **Klare Trennung der Zuständigkeiten** – jedes Arbeitspaket isoliert eine eindeutige Verantwortung (Klassifizierung, Wiederholung, veraltete Erkennung, Abbruch, Observabilität, API).  
- **Nutzung bestehender Infrastruktur** – wiederverwendet den vorhandenen `ErrorType` enum, `RecoveryService` und `TaskExecution` Modell, wodurch Duplikate reduziert werden.  
- **Klare Akzeptanzkriterien** – jedes Arbeitspaket listet messbare, testbare Kriterien auf.  
- **Risikobewusstsein** – der Überblick identifiziert bereits wichtige Risiken (Fehlklassifizierung, Rennbedingungen, Leistungsauswirkungen) und schlägt Gegenmaßnahmen vor.

## 3. Identifizierte Lücken & Risiken

| Bereich | Problem | Auswirkung | Vorgeschlagene Lösung |
|---------|---------|------------|-----------------------|
| **Vollständigkeit der Fehlerklassifizierung** | Der aktuelle `ErrorType` enum deckt möglicherweise nicht alle möglichen Fehlerarten ab (z.B. Deadlock, Ressourcenleck, externe Service-Drosselung). | Erweitere den enum um domänenspezifische Werte; füge einen Fallback `UNKNOWN` hinzu, der den Fehler als nicht wiederholbar behandelt, es sei denn, er wird explizit als wiederholbar über Konfiguration gekennzeichnet. |
| **Konfiguration des Back-off-Verfahrens** | Die Back-off-Parameter (Basis, Multiplikator, Jitter, maximale Verzögerung) sind in `RetryMatrix` hard‑kodiert. Dies beschränkt die Anpassungsfähigkeit über verschiedene Umgebungen hinweg. | Führe eine konfigurierbare Wiederholungsrichtlinie ein (z.B. über YAML/JSON-Konfiguration oder Umgebungsvariablen) und lasse `RetryMatrix` daraus lesen. |
| **Timeout-Werte für veraltete Erkennung** | Die Schwellenwerte für die veraltete Erkennung (Heartbeat-Timeout, Update-Timeout, maximale Dauer) sind in `error_classification.py` hard‑kodiert. | Verschiebe diese Schwellenwerte in das Konfigurationssystem (ähnlich wie WP4 in WORK_PACKAGES.md), damit sie pro Umgebung angepasst werden können. |
| **Abdeckung der Observabilität** | Fehlerdetails werden persistiert, aber nicht alle Fehlerfelder werden in Metriken/Tracing offengelegt (z.B. Fehlerart, Wiederholungsanzahl). | Erweitere die Observabilitätsschicht, um Fehlerart, Wiederholungsanzahl und Zeitstempel in Metriken und Traces einzubeziehen. |
| **Sicherheit der API-Endpunkte** | Falls die optionalen API-Endpunkte implementiert werden, sollten sie geschützt sein (z.B. über Authentifizierung/Autorisierung), um unbefugten Zugriff auf Fehlerdaten zu verhindern. | Füge Authentifizierungsprüfungen zu den API-Endpunkten hinzu, möglicherweise indem du die vorhandene Auth-Middleware wiederverwendest. |
| **Testabdeckung für Grenzfälle** | Die aktuellen Tests decken möglicherweise keine Grenzfälle ab wie gleichzeitige Wiederholungsversuche, Überlauf der Wiederholungszähler oder Interaktion zwischen veralteter Erkennung und Wiederholungsmechanismus. | Füge gezielte Unit- und Integrations-Tests für diese Grenzfälle hinzu. |