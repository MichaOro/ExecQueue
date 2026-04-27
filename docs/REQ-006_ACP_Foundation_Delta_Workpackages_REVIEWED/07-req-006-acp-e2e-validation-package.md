# AP-07 – ACP-End-to-End-Validierung ergänzen

## Ziel
Die ACP-Konsolidierung wird durch schlanke E2E-nahe Tests abgesichert. Die Tests decken Betriebsmodi, Health, Reachability, Restart-Verhalten und Operatorpfade ab, ohne echte externe Infrastruktur zu benötigen.

## Aufwand
Ca. 2h

## LLM-Routing
| Modell | Empfehlung | Erfolgswahrscheinlichkeit | Begründung |
|---|---:|---:|---|
| `[QWN]` | 100% | 89% | Gute Passung für testgetriebene Querschnittsvalidierung; Risiko liegt in Fixture-Isolation. |

## Fachlicher Kontext
Die Einzelpakete stabilisieren Teilbereiche. AP-07 stellt sicher, dass der Ziel-Flow aus Orchestrator, ACP-Modus, Health/Probe, API und Telegram als zusammenhängendes Verhalten regressionsarm bleibt.

## Voranalysepflicht
Vor Umsetzung prüfen und kurz dokumentieren:
- Welche Tests aus AP-01 bis AP-06 bereits existieren.
- Welche Fixtures für Settings/ENV/Health-Dateien vorhanden sind.
- Ob FastAPI-TestClient oder äquivalente Testtools genutzt werden.
- Wie HTTP-Probe und Prozessstart mockbar sind.
- Ob Tests parallel laufen und ENV-Isolation benötigen.

## Technical Specification
### Ziel-Szenarien
| Szenario | Erwartung |
|---|---|
| ACP disabled | kein Prozessstart; Health/Restart liefern kontrolliertes skipped/disabled |
| external endpoint reachable | kein lokaler Prozessstart; Probe/Health OK |
| external endpoint timeout | strukturierter Health-/API-Fehler; kein echter Netzwerkzugriff |
| local managed valid | Launch-Plan/Lifecycle nutzt Start Command, aber Test mockt Prozessstart |
| stale/missing Health-Datei | deterministischer Health-Status |
| Restart failure | API und Telegram zeigen konsistente sichere Fehlerantwort |

### Implementierungsgrenzen
- E2E-nah heißt integrierte Modulpfade, nicht echte Infrastruktur.
- Kein echter ACP-Prozess.
- Kein echter Netzwerkzugriff.
- Keine Shell-Ausführung.
- Keine breitflächige Test-Neustrukturierung.

## Umsetzungsschritte
1. Bestehende Testabdeckung aus AP-01 bis AP-06 inventarisieren.
2. Fehlende Querschnittsszenarien identifizieren.
3. Bestehende Tests erweitern; nur bei Unübersichtlichkeit neue Flow-Testdatei anlegen.
4. Fixtures für ENV, Health-Pfad, HTTP-Probe und Prozessstart sauber isolieren.
5. Tests stabil ausführen und Flakiness-Risiken entfernen.

## Akzeptanzkriterien
- Alle drei ACP-Betriebsmodi sind testseitig abgedeckt.
- Health-Staleness und Endpoint-Fehler sind deterministisch getestet.
- API- und Telegram-Fehlerfeedback ist gegen Lifecycle-Fehler abgesichert.
- Kein Test benötigt echten ACP-Prozess, Netzwerk oder Bash.
- Tests sind isoliert genug für parallele/CI-nahe Ausführung.

## Validierung
- Relevante Test-Suite lokal ausführen.
- Prüfen, dass HTTP- und Prozess-Mocks tatsächlich verwendet werden.
- ENV/Settings nach Tests zurücksetzen.
- Testnamen so wählen, dass Szenario und Erwartung lesbar sind.

## Risiken / Edge Cases
- Zu breite Tests werden langsam oder flaky.
- ENV-Leaks zwischen Tests können falsche Ergebnisse erzeugen.
- Zu starke Kopplung an Implementierungsdetails erschwert spätere Refactorings.

## Ausführungsregeln für das Dev-LLM
- Vor Codeänderung: relevante Dateien suchen, Ist-Verhalten kurz dokumentieren, vorhandene Patterns übernehmen.
- Keine Greenfield-Neustrukturierung, keine generischen Frameworks, keine präventiven Abstraktionen.
- Änderungen minimal-invasiv halten; bestehende Module erweitern, wenn fachlich passend.
- Keine Secrets, Tokens, sensitiven Pfade oder Stacktraces in Operator-Responses ausgeben.
- Externe Effekte in Tests mocken: kein echter ACP-Prozess, kein echter Netzwerkzugriff, keine Shell-Ausführung.
- Ausgabe am Ende der Umsetzung mit letzter separater Zeile exakt: `EXECQUEUE.STATUS.FINISHED`
