# AP-06 – Telegram-ACP-Operator-Feedback konsistent machen

## Ziel
`/restart acp` und der ACP-Anteil von `/restart all` nutzen die konsolidierte Lifecycle-/API-Semantik und liefern kurze, eindeutige Operator-Rückmeldungen für Erfolg, deaktiviert, extern gemanagt, ungültige Konfiguration und Fehler.

## Aufwand
Ca. 2h

## LLM-Routing
| Modell | Empfehlung | Erfolgswahrscheinlichkeit | Begründung |
|---|---:|---:|---|
| `[DSK]` | 96% | 88% | Handlernahe Anpassung; Risiko liegt primär in bestehender Telegram-Testkopplung. |

## Fachlicher Kontext
Telegram ist ein Operator-Pfad, kein zweiter Lifecycle-Manager. Der Betrieb braucht verständliche Rückmeldungen, ohne dass Telegram Sonderlogik für ACP-Start/Restart enthält.

## Voranalysepflicht
Vor Umsetzung prüfen und kurz dokumentieren:
- Aktueller Command-Handler für `/restart`, `/restart acp`, `/restart all`.
- Berechtigungs-/Adminprüfung im Telegram-Pfad.
- Bestehende Feedback-Texte und Testsnapshots.
- Wie mehrere Restart-Ziele bei `/restart all` aggregiert werden.
- Ob Fehlerdetails bisher ungefiltert ausgegeben werden.

## Technical Specification
### Feedback-Zielmatrix
| Lifecycle-Status | Telegram-Rückmeldung | Verhalten |
|---|---|---|
| `success` | ACP-Restart ausgeführt | Erfolg |
| `disabled` | ACP ist deaktiviert; kein Restart ausgeführt | skipped |
| `external_managed` | ACP wird extern verwaltet; kein lokaler Restart ausgeführt | skipped |
| `invalid_config` | ACP-Konfiguration ungültig; Details in Logs/Health prüfen | sicherer Fehler |
| `failed` | ACP-Restart fehlgeschlagen; Details in Logs/Health prüfen | sicherer Fehler |

### Implementierungsgrenzen
- Telegram delegiert an dieselbe Operation wie API oder direkt an Lifecycle-Authority.
- Kein eigener ACP-Restart-Code im Handler.
- Keine neuen Telegram-Kommandos.
- Keine Auth-Änderung.
- `/restart all` muss partielle ACP-Fehler sauber aggregieren.

## Umsetzungsschritte
1. Telegram-Restart-Handler und Tests inventarisieren.
2. LifecycleResult-/API-Result-Mapping auf Telegram-Feedback definieren.
3. Handler minimal auf gemeinsame Operation umstellen.
4. `/restart all` Aggregation prüfen und absichern.
5. Tests für relevante Status ergänzen.

## Akzeptanzkriterien
- `/restart acp` enthält keine konkurrierende ACP-Sonderlogik.
- Extern gemanagtes ACP wird nicht lokal neugestartet.
- Operator-Feedback unterscheidet Erfolg, disabled, external managed, invalid config und failed.
- `/restart all` bleibt funktionsfähig.
- Fehlertexte enthalten keine Secrets, Shell-Kommandos oder Stacktraces.

## Validierung
- Telegram-Handler-Tests mit gemockter Lifecycle-Operation.
- Test: external managed → skipped Feedback.
- Test: invalid config/failed → sichere Fehlermeldung.
- Test: `/restart all` mit gemischten Ergebnissen.

## Risiken / Edge Cases
- Textänderungen können bestehende Tests brechen.
- Sync/Async-Handlerverhalten kann Mocking erschweren.
- Zu ausführliche Fehlermeldungen können interne Details offenlegen.

## Ausführungsregeln für das Dev-LLM
- Vor Codeänderung: relevante Dateien suchen, Ist-Verhalten kurz dokumentieren, vorhandene Patterns übernehmen.
- Keine Greenfield-Neustrukturierung, keine generischen Frameworks, keine präventiven Abstraktionen.
- Änderungen minimal-invasiv halten; bestehende Module erweitern, wenn fachlich passend.
- Keine Secrets, Tokens, sensitiven Pfade oder Stacktraces in Operator-Responses ausgeben.
- Externe Effekte in Tests mocken: kein echter ACP-Prozess, kein echter Netzwerkzugriff, keine Shell-Ausführung.
- Ausgabe am Ende der Umsetzung mit letzter separater Zeile exakt: `EXECQUEUE.STATUS.FINISHED`
