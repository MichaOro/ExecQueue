# REQ-006 – ACP Foundation Delta – Qualitätsüberarbeitete Arbeitspakete

## TL;DR
REQ-006 ist eine Konsolidierung der vorhandenen ACP-Basis, keine Neuimplementierung. Die Arbeitspakete stabilisieren Betriebsvertrag, Health-/Reachability-Semantik, Lifecycle-Authority, Admin-API, Telegram-Operatorpfad und E2E-nahe Validierung als belastbaren Unterbau für den ExecQueue-Flow.

## Zielbeitrag zum ExecQueue-Flow
| Flow-Bereich | Benötigte ACP-Grundlage | Abdeckung |
|---|---|---|
| Orchestrator prüft ausführbare Tasks | eindeutiger ACP-Betriebsmodus | AP-01 |
| Runner / ACP Session wird gestartet oder extern genutzt | Lifecycle-Authority + Modusregeln | AP-01, AP-04 |
| ACP Responses / Events werden belastbar eingeordnet | Health + Reachability | AP-02, AP-03 |
| Operator kann kontrolliert eingreifen | Admin-API + Telegram-Feedback | AP-05, AP-06 |
| Fehlerfälle bleiben reproduzierbar | E2E-nahe Tests | AP-07 |

## Qualitätsbewertung der Ursprungsversion
Die vorhandenen APs waren fachlich solide geschnitten. Für direkten Dev-Handover fehlten aber an mehreren Stellen verbindlichere Verträge, klare Out-of-Scope-Grenzen, konkrete Fehlersemantik, Edge-Case-Abdeckung, Validierungserwartungen und eine explizite Kopplung an den ExecQueue-Flow.

## Umsetzungsreihenfolge
1. AP-01 – ACP-Betriebsmodell und Konfigurationsvertrag
2. AP-02 – ACP-Health-Pfad und Statussemantik
3. AP-03 – ACP-Reachability- und Protocol-Probe
4. AP-04 – ACP-Lifecycle-Authority
5. AP-05 – ACP-Admin-API Minimal-v1
6. AP-06 – Telegram-ACP-Operator-Feedback
7. AP-07 – ACP-End-to-End-Validierung

## Schnittprinzipien
- AP-01 schafft die fachliche Wahrheit für alle Folgepakete.
- AP-02 und AP-03 trennen dateibasierte Health-Semantik von technischer Endpoint-Erreichbarkeit.
- AP-04 verhindert konkurrierende Restart-/Startpfade.
- AP-05 stabilisiert den API-Vertrag bewusst minimal.
- AP-06 erzeugt keine Telegram-Sonderlogik.
- AP-07 validiert querschnittlich, ersetzt aber keine Unit-Tests in AP-01 bis AP-06.

## Nicht-Ziele
- keine vollständige ACP-Admin-Konsole,
- keine Start-/Stop-Endpunkte ohne belastbaren Vertrag,
- keine DB-Migrationen, sofern ACP-Status nicht persistiert werden muss,
- keine echte Prozess-/Netzwerkabhängigkeit in Tests,
- keine Entfernung vorhandener Shell-Skripte ohne Nutzungsnachweis.
