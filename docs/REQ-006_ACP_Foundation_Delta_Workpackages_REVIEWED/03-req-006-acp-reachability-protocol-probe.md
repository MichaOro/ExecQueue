# AP-03 – ACP-Reachability- und Protocol-Probe ergänzen

## Ziel
ACP wird zusätzlich über `ACP_ENDPOINT_URL` technisch geprüft, damit Prozessstatus, Health-Datei und tatsächliche Endpoint-Erreichbarkeit sauber unterschieden werden.

## Aufwand
Ca. 2h

## LLM-Routing
| Modell | Empfehlung | Erfolgswahrscheinlichkeit | Begründung |
|---|---:|---:|---|
| `[QWN]` | 100% | 90% | Technisch klar, aber mit Risiko durch HTTP-/Timeout-/Async-Details. |

## Fachlicher Kontext
Für den ExecQueue-Flow reicht „lokaler Prozess läuft“ nicht. OpenCode ACP muss erreichbar sein und erwartbar antworten. Im Modus `external_endpoint` ist die Probe die entscheidende Verfügbarkeitsquelle.

## Voranalysepflicht
Vor Umsetzung prüfen und kurz dokumentieren:
- Ob `ACP_ENDPOINT_URL` Basis-URL oder vollständiger Health-/Status-Endpunkt ist.
- Welcher minimale ACP-Endpunkt stabil verfügbar ist.
- Welcher HTTP-Client bereits verwendet wird.
- Ob Health-Checks synchron oder asynchron laufen.
- Bestehende Timeout-/Retry-Patterns.

## Technical Specification
### Zielvertrag `ProbeResult`
- `reachable: boolean`
- `status: ok | timeout | http_error | protocol_mismatch | invalid_url | skipped`
- optional `latency_ms`
- `message` kurz und sanitisiert

### Implementierungsgrenzen
- Kurzer Timeout; kein blockierender Langläufer im Health-Pfad.
- Kein echter Netzwerkzugriff in Tests.
- Kein umfangreicher ACP-Protokollparser; nur Minimalprobe.
- Keine Retry-Logik, außer ein vorhandenes Projektpattern verlangt sie.
- Bei `disabled` wird die Probe übersprungen.
- Bei `external_endpoint` darf fehlender lokaler Prozess nicht als Fehler zählen, solange Probe erfolgreich ist.

## Umsetzungsschritte
1. Semantik von `ACP_ENDPOINT_URL` und Minimalprobe festlegen.
2. Kleine Probe-Funktion ergänzen oder bestehende Health-Funktion erweitern.
3. Timeout- und Fehlerbehandlung strukturiert abbilden.
4. Probe-Ergebnis in ACP-Health integrieren.
5. Tests für reachable, timeout, HTTP-Fehler, invalid URL, protocol mismatch ergänzen.

## Akzeptanzkriterien
- Endpoint-Erreichbarkeit wird unabhängig vom lokalen Prozessstatus bewertet.
- `external_endpoint` kann ohne lokalen Prozess `OK` werden, wenn der Endpoint erreichbar ist.
- Timeout/HTTP-Fehler/ungültige URL liefern reproduzierbare Statusinformationen.
- Health-Check bleibt schnell und nicht flaky.

## Validierung
- HTTP-Client mocken.
- Timeout deterministisch simulieren.
- Test: disabled → Probe skipped.
- Test: external endpoint reachable → kein lokaler Prozess notwendig.

## Risiken / Edge Cases
- Unklarer ACP-Minimalendpoint kann zu falscher Probe führen.
- Sync/Async-Mismatch kann Health instabil machen.
- Zu harte Protokollprüfung kann kompatible ACP-Versionen fälschlich ablehnen.

## Ausführungsregeln für das Dev-LLM
- Vor Codeänderung: relevante Dateien suchen, Ist-Verhalten kurz dokumentieren, vorhandene Patterns übernehmen.
- Keine Greenfield-Neustrukturierung, keine generischen Frameworks, keine präventiven Abstraktionen.
- Änderungen minimal-invasiv halten; bestehende Module erweitern, wenn fachlich passend.
- Keine Secrets, Tokens, sensitiven Pfade oder Stacktraces in Operator-Responses ausgeben.
- Externe Effekte in Tests mocken: kein echter ACP-Prozess, kein echter Netzwerkzugriff, keine Shell-Ausführung.
- Ausgabe am Ende der Umsetzung mit letzter separater Zeile exakt: `EXECQUEUE.STATUS.FINISHED`
