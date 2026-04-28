# LLM Routing

| Paket | Modell | Begründung | Risiko |
|---|---|---|---:|
| 01 Status and Task Metadata | `[QWN]` | Pattern-nahe Modell-/Schema-Erweiterung | Mittel |
| 02 Trigger and Candidate Discovery | `[QWN]` | Deterministische Query-/Service-Logik | Mittel |
| 03 Classification and Batch Planning | `[GPT]` | Architektur- und Parallelisierungslogik | Hoch |
| 04 Atomic Locking and Queued Transition | `[GPT]` | Concurrency-kritisch | Sehr hoch |
| 05 Write Git Context Preparation | `[GPT]` | Git-/Filesystem-/Security-Seiteneffekte | Hoch |
| 06 Prepared Context Contract | `[QWN]` | DTO-/Validation-/Serialization-lastig | Mittel |
| 07 Failure and Stale Recovery | `[GPT]` | Fehler-/Recovery-Matrix und Side Effects | Hoch |
| 08 Observability and E2E Validation | `[QWN]` | Tests/Logs, klarer Scope | Mittel |
| 09 Flow Alignment and Documentation | `[QWN]` | Dokumentation/PUML-Abgleich | Niedrig |

## Strategische Empfehlung
Die drei Pakete `03`, `04` und `05` sollten nicht parallel durch voneinander unabhängige Coding-Agent-Sessions umgesetzt werden, wenn keine sehr klare Contract-Datei vorliegt. Das Risiko von divergierenden Annahmen zu Branch-/Batch-/Locking-Semantik ist hoch.

Empfohlen:
1. `01` und `02` parallel möglich.
2. `03` danach als Architekturanker.
3. `04` nach `03`.
4. `05` und `06` danach, aber mit gemeinsamem `PreparedExecutionContext.v1` Contract.
5. `07` nach `05`, weil Recovery Side-Effect-State kennen muss.
6. `08` und `09` zum Abschluss.
