# AP-05 – ACP-Admin-API-Vertrag als Minimal-v1 festlegen

## Ziel
Der ACP-Admin-API-Vertrag wird bewusst minimal stabilisiert: Restart und Health sind offiziell; `start`, `stop` und ein separater `status` werden nicht halb implementiert, solange deren Semantik nicht belastbar definiert ist.

## Aufwand
Ca. 2h

## LLM-Routing
| Modell | Empfehlung | Erfolgswahrscheinlichkeit | Begründung |
|---|---:|---:|---|
| `[GPT]` | 106% | 93% | API-Vertrag erfordert klare Grenzziehung und saubere Fehlersemantik. |

## Fachlicher Kontext
`POST /api/system/acp/restart` und `/acp/health` existieren bereits. Für REQ-006 ist Stabilisierung wichtiger als API-Ausbau; halb definierte Admin-Endpunkte würden Operator und Orchestrator unterschiedliche Wahrheiten geben.

## Voranalysepflicht
Vor Umsetzung prüfen und kurz dokumentieren:
- Aktuelle Routenpräfixe und Response-Formate.
- Vorhandene Auth-/Admin-Gates für Systemrouten.
- Bestehende OpenAPI-/Dokumentationsmechanismen.
- Ob Clients konkrete Response-Felder erwarten.
- Wie Health und Restart Fehler ausgeben.

## Technical Specification
### Minimal-v1 Vertrag
| Endpoint | Status | Zweck |
|---|---|---|
| ACP-Health-Pfad | offiziell | ACP-Zustand/Reachability lesen |
| `POST /api/system/acp/restart` | offiziell | ACP-Restart gemäß Lifecycle-Authority anfordern |
| `POST /acp/start` | nicht Bestandteil | vermeiden bis Start-Semantik stabil ist |
| `POST /acp/stop` | nicht Bestandteil | vermeiden bis Stop-Semantik stabil ist |
| `GET /acp/status` | nicht Bestandteil, falls Health reicht | keine Doppelung zu Health |

### Response-Mindestfelder
- `ok: boolean`
- `status` aus Lifecycle-/Health-Semantik
- `message` kurz und sanitisiert
- optional `mode` aus AP-01

## Umsetzungsschritte
1. Bestehende ACP-Routen und Tests identifizieren.
2. Minimal-v1 im Code/Dokumentationskontext fixieren.
3. Restart-Response an LifecycleResult angleichen.
4. Verhalten für disabled/external/local/invalid/failed testen.
5. Nicht-Ziele `start`, `stop`, `status` dokumentieren.

## Akzeptanzkriterien
- Restart-Endpoint hat einen klaren, getesteten Vertrag.
- Health und Restart verwenden dieselbe Statussprache.
- API umgeht den `ACPLifecycleManager` nicht.
- `start`, `stop`, `status` werden nicht als Stub oder halb funktionsfähig eingeführt.
- Fehlerantworten sind operator-tauglich und sicher.

## Validierung
- API-Test für Erfolg, disabled, external managed, invalid config und Lifecycle-Fehler.
- Keine echten Prozesse/Netzwerkzugriffe.
- Falls OpenAPI-Doku existiert: prüfen, dass Minimal-v1 sichtbar ist.

## Risiken / Edge Cases
- Bestehende Clients könnten altes Response-Format erwarten.
- Routenpräfixe können uneinheitlich sein.
- Separater Status-Endpunkt wäre semantische Doppelung zu Health.

## Ausführungsregeln für das Dev-LLM
- Vor Codeänderung: relevante Dateien suchen, Ist-Verhalten kurz dokumentieren, vorhandene Patterns übernehmen.
- Keine Greenfield-Neustrukturierung, keine generischen Frameworks, keine präventiven Abstraktionen.
- Änderungen minimal-invasiv halten; bestehende Module erweitern, wenn fachlich passend.
- Keine Secrets, Tokens, sensitiven Pfade oder Stacktraces in Operator-Responses ausgeben.
- Externe Effekte in Tests mocken: kein echter ACP-Prozess, kein echter Netzwerkzugriff, keine Shell-Ausführung.
- Ausgabe am Ende der Umsetzung mit letzter separater Zeile exakt: `EXECQUEUE.STATUS.FINISHED`
