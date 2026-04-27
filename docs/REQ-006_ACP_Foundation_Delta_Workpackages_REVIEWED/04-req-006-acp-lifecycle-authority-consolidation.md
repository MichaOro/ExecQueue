# AP-04 – ACP-Lifecycle-Authority konsolidieren

## Ziel
`ACPLifecycleManager` wird als fachlich führender Pfad für ACP-Lifecycle-Operationen bestätigt oder hergestellt. API, Telegram und Orchestrator dürfen keine konkurrierenden Restart-/Startentscheidungen mit eigener Semantik enthalten.

## Aufwand
Ca. 2h

## LLM-Routing
| Modell | Empfehlung | Erfolgswahrscheinlichkeit | Begründung |
|---|---:|---:|---|
| `[GPT]` | 110% | 91% | Zentraler Authority-Schnitt mit höherem Seiteneffekt-Risiko in API/Telegram/Orchestrator. |

## Fachlicher Kontext
Im ExecQueue-Flow erzeugt der Orchestrator Runner und startet OpenCode ACP Sessions. Parallele Restart-Pfade über API, Telegram oder Shell dürfen den ACP-Zustand nicht unkoordiniert verändern.

## Voranalysepflicht
Vor Umsetzung prüfen und kurz dokumentieren:
- Welche Pfade ACP aktuell starten/restarten: Orchestrator, API, Telegram, Shell-Skript.
- Ob `ops/scripts/acp_restart.sh` produktiv genutzt wird.
- Welche Resultate/Exceptions `ACPLifecycleManager` aktuell liefert.
- Wie externe vs. lokale Modi behandelt werden.
- Ob Locks/Guards für gleichzeitige Restart-Versuche existieren.

## Technical Specification
### Zielvertrag `LifecycleResult`
- `status: success | skipped | disabled | external_managed | invalid_config | failed`
- `operation` nur für vorhandene Operationen verwenden
- `message` sanitisiert
- optional `details` ohne Secrets

### Implementierungsgrenzen
- API und Telegram delegieren an dieselbe fachliche Operation oder einen sehr kleinen Operations-Service.
- Shell-Skript bleibt Wrapper/Legacy-Hilfsmittel, aber nicht fachliche Wahrheit.
- Kein generischer Command-Bus.
- Kein Start-/Stop-Ausbau, wenn nur Restart stabilisiert werden soll.
- Extern gemanagtes ACP wird nicht lokal restarted.

## Umsetzungsschritte
1. Alle ACP-Lifecycle-Aufrufketten inventarisieren.
2. Führenden Lifecycle-Pfad festlegen und dokumentieren.
3. Result-/Fehlersemantik minimal vereinheitlichen.
4. API und Telegram auf dieselbe Operation verdrahten.
5. Shell-Skript als Wrapper/Legacy prüfen.
6. Tests für Delegation und Fehlerübersetzung ergänzen.

## Akzeptanzkriterien
- ACP-Restart hat genau eine fachliche Authority.
- API und Telegram verwenden dieselbe Lifecycle-Operation oder denselben kleinen Operations-Service.
- Extern gemanagtes ACP wird kontrolliert skipped, nicht lokal neugestartet.
- Fehlerfälle werden konsistent und sanitisiert zurückgegeben.
- Bestehender Orchestrator-Autostart regressiert nicht.

## Validierung
- Unit-Test: API delegiert an Lifecycle-Authority.
- Unit-Test: Telegram delegiert an Lifecycle-Authority.
- Test: external endpoint → kein lokaler Restart.
- Test: Lifecycle-Fehler → konsistente Result-Struktur.

## Risiken / Edge Cases
- Shell-Skript könnte produktiv direkt genutzt werden.
- Gleichzeitige Restart-Versuche können Race Conditions erzeugen.
- Zu starke Vereinheitlichung kann legitime Spezialfälle entfernen.

## Ausführungsregeln für das Dev-LLM
- Vor Codeänderung: relevante Dateien suchen, Ist-Verhalten kurz dokumentieren, vorhandene Patterns übernehmen.
- Keine Greenfield-Neustrukturierung, keine generischen Frameworks, keine präventiven Abstraktionen.
- Änderungen minimal-invasiv halten; bestehende Module erweitern, wenn fachlich passend.
- Keine Secrets, Tokens, sensitiven Pfade oder Stacktraces in Operator-Responses ausgeben.
- Externe Effekte in Tests mocken: kein echter ACP-Prozess, kein echter Netzwerkzugriff, keine Shell-Ausführung.
- Ausgabe am Ende der Umsetzung mit letzter separater Zeile exakt: `EXECQUEUE.STATUS.FINISHED`
