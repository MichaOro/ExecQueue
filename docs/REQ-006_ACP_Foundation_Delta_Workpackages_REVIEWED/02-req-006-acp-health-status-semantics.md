# AP-02 – ACP-Health-Pfad und Statussemantik konsolidieren

## Ziel
ACP-Health verwendet für Schreib- und Lesepfad dieselbe Quelle und bildet ACP-Zustände konsistent auf globale Health-Semantik ab. `/health`, `/acp/health` und interne Lifecycle-Zustände dürfen sich nicht widersprechen.

## Aufwand
Ca. 2h

## LLM-Routing
| Modell | Empfehlung | Erfolgswahrscheinlichkeit | Begründung |
|---|---:|---:|---|
| `[QWN]` | 100% | 92% | Klar umrissene Konsolidierung mit moderatem Testfokus. |

## Fachlicher Kontext
Der ExecQueue-Flow bewertet Ausführbarkeit und Operatorzustand indirekt über ACP-Health. Falsche Pfade oder uneinheitliche Statuswerte führen zu instabilem Runner-/Session-Verhalten.

## Voranalysepflicht
Vor Umsetzung prüfen und kurz dokumentieren:
- Wo `ops/health/acp.json` geschrieben und gelesen wird.
- Ob relative Pfade vom Working Directory abhängen.
- Welche Statuswerte aktuell existieren.
- Ob Health-Registry und ACP-spezifischer Endpoint dieselbe Logik nutzen.

## Technical Specification
### Zielsemantik
| ACP-Zustand | Health-Semantik | Hinweis |
|---|---|---|
| `disabled` | `OK` oder `SKIPPED` gemäß Pattern | bewusst deaktiviert |
| `starting` | `DEGRADED` | temporär nicht voll einsatzbereit |
| `running` | `OK` | valide, nicht stale |
| `failed` | `ERROR` | sanitisiertes Fehlerdetail |
| `missing` | definierter Fehlerstatus | Datei fehlt |
| `stale` | definierter Fehlerstatus | Datei veraltet |
| `invalid_config` | `ERROR` | Konfigurationsvertrag verletzt |

### Implementierungsgrenzen
- Pfaddefinition zentralisieren.
- Reader/Writer dürfen keine unterschiedlichen relativen Pfade verwenden.
- Registry und `/acp/health` verwenden denselben Check.
- Staleness testbar machen, ohne Echtzeitflakiness.

## Umsetzungsschritte
1. Reader-/Writer-Pfade und Statuswerte inventarisieren.
2. Zentrale Pfadquelle etablieren.
3. Statusmapping an vorhandene Health-Enums angleichen.
4. Registry- und Endpoint-Anbindung vereinheitlichen.
5. Tests für valid/missing/stale/failed ergänzen.

## Akzeptanzkriterien
- Read-/Write-Pfad ist identisch und getestet.
- `/health` und `/acp/health` widersprechen sich bei ACP nicht.
- Missing/stale Health-Dateien liefern deterministische Statusinformationen.
- Fehlerdetails sind operator-tauglich, aber ohne Secrets/Stacktraces.

## Validierung
- Unit-Tests mit temporärem Health-Verzeichnis.
- Tests für stale/missing/corrupt Health-Datei.
- Endpoint-/Registry-Test auf identische ACP-Bewertung.

## Risiken / Edge Cases
- Relative Pfade können lokal und CI unterschiedlich wirken.
- Monitoring-Erwartungen können von Statusänderungen betroffen sein.
- Zu detaillierte Fehlertexte können Runtime-Details leaken.

## Ausführungsregeln für das Dev-LLM
- Vor Codeänderung: relevante Dateien suchen, Ist-Verhalten kurz dokumentieren, vorhandene Patterns übernehmen.
- Keine Greenfield-Neustrukturierung, keine generischen Frameworks, keine präventiven Abstraktionen.
- Änderungen minimal-invasiv halten; bestehende Module erweitern, wenn fachlich passend.
- Keine Secrets, Tokens, sensitiven Pfade oder Stacktraces in Operator-Responses ausgeben.
- Externe Effekte in Tests mocken: kein echter ACP-Prozess, kein echter Netzwerkzugriff, keine Shell-Ausführung.
- Ausgabe am Ende der Umsetzung mit letzter separater Zeile exakt: `EXECQUEUE.STATUS.FINISHED`
