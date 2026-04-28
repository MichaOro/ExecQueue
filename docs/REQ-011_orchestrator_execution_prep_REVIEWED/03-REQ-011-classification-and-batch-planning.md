# 03 — Task Classification and Safe Batch Planning

## Ziel
Executable Candidates deterministisch in Read-only/Write und Sequential/Parallel klassifizieren und daraus einen sicheren transienten Batch-Plan bilden.

## Aufwand
Ca. 2h

## Scope
Enthalten:
- Reine Klassifikation ohne Seiteneffekte.
- Transienter Batch-Plan.
- Konservative Defaults.
- Konfliktgruppen für Write-Tasks.

Nicht enthalten:
- DB-Lock.
- Statusänderung.
- Git-/Filesystem-Operationen.

## Klassifikationsregeln
Defaulting:
- Fehlendes `requires_write_access` => `write`.
- Fehlender `parallelization_mode` => `sequential`.
- Unbekannte Task-Typen => nicht planen oder konservativ `write + sequential` markieren.

Batch-Kategorien:
1. `readonly_parallel`
   - mehrere Tasks erlaubt
   - kein Branch/Worktree
2. `write_parallel_isolated`
   - mehrere Tasks erlaubt
   - nur, wenn jeder Task eigenen isolierten Branch/Worktree bekommen kann
3. `write_sequential`
   - genau ein Task oder explizit serialisierte Konfliktgruppe
   - Pflicht bei gleicher expliziter Branch, unklarem mutable Context oder unbekannter Parallelisierbarkeit

## Technical Specification
- `TaskClassification` DTO:
  - `task_id`
  - `requires_write_access`
  - `parallelization_mode`
  - `effective_runner_mode`
  - `conflict_key`
  - `reason_codes[]`
- `BatchPlan` DTO:
  - `batch_id`
  - `batch_type`
  - `task_ids[]`
  - `excluded_task_ids[]`
  - `exclusion_reasons`
- Branch-Konfliktregel:
  - gleiche explizite Branch bei mehreren Write-Tasks => nicht parallel
  - fehlende Branch bei parallelem Write ist erlaubt, wenn pro Task deterministisch eine eigene Branch erzeugt wird
- Plan bleibt transient bis Paket 04 lockt.

## Umsetzungsschritte
1. DTOs definieren.
2. Klassifikationsfunktion implementieren.
3. Konservative Defaults implementieren.
4. Konflikt-Key bestimmen: Branch, Repo, Requirement/Resource-Key oder expliziter Lock-Key.
5. Batch-Typen bilden und Limits anwenden.
6. Unit-Tests für Defaulting, Parallelisierung und Konfliktfälle ergänzen.

## Akzeptanzkriterien
- Jede Candidate Task erhält eine deterministische Klassifikation.
- Fehlende Metadaten führen nie zu optimistischer Parallelisierung.
- Read-only Tasks können gemeinsam geplant werden.
- Write Tasks teilen keinen mutable Kontext parallel ohne explizite Isolation.
- Der Batch-Plan erzeugt keine DB- oder Git-Seiteneffekte.

## Risiken / Prüfpunkte
- Keine Freitext-Inferenz aus Task-Beschreibungen.
- Branch-Konflikte nicht erst beim Git-Resolver entdecken.
- Keine Persistenz des Plans vor erfolgreichem Locking.

## Modellrouting
`[GPT]` — höhere Architektur- und Concurrency-Ambiguität.
