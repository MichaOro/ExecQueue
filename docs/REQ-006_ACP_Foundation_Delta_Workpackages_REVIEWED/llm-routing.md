# LLM Routing – REQ-006 ACP Foundation Delta

## Routing-Tabelle
| AP | Arbeitspaket | Modell | Empfehlung | Erfolgswahrscheinlichkeit | Grund |
|---:|---|---|---:|---:|---|
| 01 | ACP-Betriebsmodell und Konfigurationsvertrag | `[GPT]` | 108% | 94% | Zentraler Vertrags- und Architekturentscheid mit hoher Folgewirkung. |
| 02 | ACP-Health-Pfad und Statussemantik | `[QWN]` | 100% | 92% | Klare Konsolidierung, gut testbar. |
| 03 | ACP-Reachability- und Protocol-Probe | `[QWN]` | 100% | 90% | Technisch fokussiert, Risiko durch Timeout/HTTP/Async. |
| 04 | ACP-Lifecycle-Authority | `[GPT]` | 110% | 91% | Höchstes Konsolidierungsrisiko durch API/Telegram/Orchestrator-Kopplung. |
| 05 | ACP-Admin-API Minimal-v1 | `[GPT]` | 106% | 93% | API-Vertrag und Nicht-Ziele müssen sauber abgegrenzt werden. |
| 06 | Telegram-ACP-Operator-Feedback | `[DSK]` | 96% | 88% | Handlernah, klein, aber test-/textsensitiv. |
| 07 | ACP-End-to-End-Validierung | `[QWN]` | 100% | 89% | Querschnittstests mit Fixture-/Mocking-Fokus. |

## Modelllegende
- `[QWN]` Qwen 3.5 122B: Baseline für fokussierte Implementierungs- und Testpakete.
- `[DSK]` DeepSeek V4 Flash: geeignet für klar begrenzte Handler-/Mapping-Aufgaben.
- `[GPT]` GPT-5.4: bevorzugt bei Architektur-, Vertrags-, Konsolidierungs- und Risikoentscheidungen.

## Bewertungslogik
- Empfehlung bewertet relative Eignung gegenüber `[QWN] = 100%`.
- Erfolgswahrscheinlichkeit bewertet Umsetzungssicherheit nach verpflichtender Codebasis-Verifikation.
- Werte über 100% bei Empfehlung bedeuten Modellpassung, nicht garantierten Erfolg.
