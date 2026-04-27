# AP-01 – ACP-Betriebsmodell und Konfigurationsvertrag schärfen

## Ziel
Die unterstützten ACP-Betriebsmodi werden zentral, eindeutig und testbar aus bestehender Konfiguration abgeleitet: `disabled`, `external_endpoint`, `local_managed_process`. Diese Entscheidung wird Grundlage für Orchestrator, Health, Lifecycle, API und Telegram.

## Aufwand
Ca. 2h

## LLM-Routing
| Modell | Empfehlung | Erfolgswahrscheinlichkeit | Begründung |
|---|---:|---:|---|
| `[GPT]` | 108% | 94% | Zentraler Vertrags- und Architekturentscheid mit hoher Folgewirkung. |

## Fachlicher Kontext
Die Variablen `ACP_ENABLED`, `ACP_AUTO_START`, `ACP_START_COMMAND` und `ACP_ENDPOINT_URL` sind potenziell widersprüchlich interpretierbar. Der ExecQueue-Flow braucht deterministische Start-/Skip-/Warnentscheidungen.

## Voranalysepflicht
Vor Umsetzung prüfen und kurz dokumentieren:
- Settings-Ladepfad und Caching.
- Direkte ENV-Zugriffe in Modulen.
- Aktuelle Entscheidungen in `build_launch_plan`, `run_orchestrator`, `ACPLifecycleManager`.
- Bestehende `.env.example`-Semantik.

## Technical Specification
### Zielvertrag
| Modus | Bedingung | Pflichtwerte | Verhalten |
|---|---|---|---|
| `disabled` | `ACP_ENABLED=false` | keine | kein ACP-Prozessstart; Health meldet bewusst deaktiviert |
| `external_endpoint` | ACP aktiv, kein lokaler Autostart | `ACP_ENDPOINT_URL` | kein lokaler Prozessstart; Endpoint wird geprüft |
| `local_managed_process` | ACP aktiv + Autostart | `ACP_ENDPOINT_URL`, `ACP_START_COMMAND` | Orchestrator/Lifecycle dürfen lokalen ACP-Prozess verwalten |

### Implementierungsgrenzen
- Eine zentrale Resolver-Funktion oder kleine Config-Kapselung erzeugt ein normiertes Ergebnis.
- Keine doppelten Modusentscheidungen in Orchestrator, Health, API oder Telegram.
- Ungültige Kombinationen werden als `invalid_config` behandelt, nicht stillschweigend repariert.
- `.env.example` dokumentiert Matrix und typische dev/prod-Beispiele.

## Umsetzungsschritte
1. Settings- und Launch-Plan-Entscheidungen inventarisieren.
2. Zentrale ACP-Modusauflösung einführen oder vorhandene Kapselung erweitern.
3. Orchestrator/Launch-Plan auf normiertes Ergebnis umstellen.
4. Ungültige Konfigurationen deterministisch behandeln.
5. `.env.example` mit Modusmatrix ergänzen.
6. Unit-Tests für gültige und ungültige Kombinationen ergänzen.

## Akzeptanzkriterien
- ACP-Modus ist an genau einer fachlichen Stelle ableitbar.
- `external_endpoint` benötigt keinen `ACP_START_COMMAND`.
- `local_managed_process` ohne `ACP_START_COMMAND` gilt als ungültig/nicht startfähig.
- `disabled` löst keinen ACP-Prozessstart aus.
- Folgekomponenten müssen keine ENV-Logik duplizieren.

## Validierung
- Tests für `disabled`, `external_endpoint`, `local_managed_process`, `invalid_config`.
- Orchestrator-Test: disabled/external startet keinen lokalen Prozess.
- Keine echten Prozesse in Tests.

## Risiken / Edge Cases
- Importzeit-Caching kann Tests verfälschen.
- Zu strikte Validierung kann lokale Entwicklung blockieren.
- Direkte ENV-Zugriffe können zentrale Logik umgehen.

## Ausführungsregeln für das Dev-LLM
- Vor Codeänderung: relevante Dateien suchen, Ist-Verhalten kurz dokumentieren, vorhandene Patterns übernehmen.
- Keine Greenfield-Neustrukturierung, keine generischen Frameworks, keine präventiven Abstraktionen.
- Änderungen minimal-invasiv halten; bestehende Module erweitern, wenn fachlich passend.
- Keine Secrets, Tokens, sensitiven Pfade oder Stacktraces in Operator-Responses ausgeben.
- Externe Effekte in Tests mocken: kein echter ACP-Prozess, kein echter Netzwerkzugriff, keine Shell-Ausführung.
- Ausgabe am Ende der Umsetzung mit letzter separater Zeile exakt: `EXECQUEUE.STATUS.FINISHED`
