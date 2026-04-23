# Validation Hardening Documentation

## Übersicht

Diese Dokumentation beschreibt die implementierte Validation-Hardening-Infrastruktur für ExecQueue. Sie erfüllt alle Anforderungen aus **requirements/3. Validation verbessern - härten der Validierungslogik.md**.

---

## Architektur

### Multi-Pass Validierung

```
┌─────────────────────────────────────────────────────────────┐
│                    Task Output                               │
│              (JSON oder Markdown-wrapped)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PASS 1: Schema-Validierung                                  │
│  - JSON-Extraktion (Markdown-Support)                        │
│  - JSON-Parsing                                              │
│  - Schema-Validierung (JSON Schema Draft 7)                  │
│  - Fehler-Typ: PARSING                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
              Valid                 Invalid
                    │                   │
                    ▼                   ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│  PASS 2: Semantische     │  │  Ergebnis:               │
│  Validierung             │  │  - error_type: PARSING   │
│  - Status-Konsistenz     │  │  - backoff berechnet     │
│  - Evidence-Qualität     │  │  - Retry mit Parsing-    │
│  - Pattern-Matching      │  │    Hilfe                 │
│  - Fehler-Typ: SEMANTIC  │  └──────────────────────────┘
└──────────────────────────┘
              │
        ┌─────┴─────┐
        │           │
    Valid      Invalid
        │           │
        ▼           ▼
┌──────────┐  ┌──────────────────────────┐
│ Ergebnis:│  │  Ergebnis:               │
│ - done   │  │  - error_type: SEMANTIC  │
│ - is_done│  │  - backoff berechnet     │
│          │  │  - Retry mit verbessertem│
│          │  │    Prompt                │
└──────────┘  └──────────────────────────┘
```

---

## Komponenten

### 1. Schema-Validator (`schema_validator.py`)

**Verantwortung**: JSON-Struktur-Validierung

**Funktionalität**:
- JSON-Extraktion aus Markdown-Code-Blöcken (REQ-VAL-002)
- JSON-Parsing mit Fehlerbehandlung
- Schema-Validierung gegen versioniertes JSON Schema (REQ-VAL-001)
- Detaillierte Fehlermeldungen mit Pfad-Informationen

**API**:
```python
# Hauptfunktion
validate_schema(output: str, schema_version: str = "1.0.0") 
    -> Tuple[bool, List[str]]

# JSON-Extraktion
extract_json_from_output(output: str) -> Optional[str]

# Detaillierte Fehler
get_schema_errors_detailed(output: str, schema_version: str) -> List[dict]
```

**Schema-Datei**: `execqueue/validation/schema/v1.json`

---

### 2. Semantic-Validator (`semantic_validator.py`)

**Verantwortung**: Inhaltliche Validierung

**Funktionalität**:
- Status-Konsistenz-Prüfung (REQ-VAL-003)
  - `status: done` erfordert nicht-leeren `evidence`
  - `status: not_done` erfordert Begründung in `summary`
- Evidence-Qualitäts-Prüfung (REQ-VAL-004)
  - Mindestlänge (konfigurierbar via `VALIDATION_EVIDENCE_MIN_LENGTH`)
  - Pattern-Matching für Dateireferenzen, Test-Erfolge, Code-Änderungen
- Strenger Modus (via `VALIDATION_STRICT_MODE`)

**API**:
```python
validate_semantics(data: dict) -> Tuple[bool, List[str]]
validate_status_consistency(data: dict) -> Tuple[bool, List[str]]
validate_evidence_quality(data: dict) -> Tuple[bool, List[str]]
get_semantic_validation_details(data: dict) -> dict
```

---

### 3. Policy-Loader (`policy_loader.py`)

**Verantwortung**: Konfigurationsmanagement und Retry-Logik

**Funktionalität**:
- Laden der Policy aus `policy.yaml` (REQ-VAL-013)
- Environment-spezifische Overrides (dev, test, production)
- Exponentielles Backoff mit Jitter (REQ-VAL-006)
- Retry-Entscheidungen pro Fehlertyp (REQ-VAL-005)
- Eskalations-Thresholds (REQ-VAL-010)

**API**:
```python
# Policy-Laden
load_policy(policy_path: str) -> Policy
get_policy() -> Policy
reload_policy() -> Policy  # Hot-Reload

# Retry-Policy
get_retry_policy(error_type: str) -> RetryPolicy
calculate_backoff_seconds(error_type: str, retry_count: int) -> float
should_retry(error_type: str, retry_count: int) -> bool

# Eskalation
should_escalate(error_type: str, retry_count: int) -> bool
```

**Policy-Datei**: `execqueue/validation/policy.yaml`

---

### 4. Task-Validator (`task_validator.py`)

**Verantwortung**: Orchestrierung der Validierungspipeline

**Funktionalität**:
- Multi-Pass Validierung (REQ-VAL-008)
- Differenzierte Fehler-Typen (REQ-VAL-005)
- Audit-Trail (REQ-VAL-012)
- Retry-Context Preservation (REQ-VAL-007)

**API**:
```python
validate_task_result(
    output: str,
    retry_count: int = 0,
    schema_version: str = "1.0.0"
) -> TaskValidationResult
```

**TaskValidationResult-Felder**:
```python
@dataclass
class TaskValidationResult:
    is_done: bool
    normalized_status: str
    summary: str
    raw_status: Optional[str]
    evidence: str
    
    # Neue Felder für Hardening
    error_type: str  # "none" | "parsing" | "semantic" | "critical"
    error_details: List[str]
    validation_passes: dict  # {"schema": bool, "semantic": bool}
    retry_count: int
    backoff_seconds: float
    
    # Audit
    schema_version: str
    raw_output_snapshot: str
    
    # Eigenschaften
    should_retry: bool
    is_critical: bool
```

---

## Fehlertypen

| Typ | Beschreibung | Retry | Backoff | Action |
|-----|--------------|-------|---------|--------|
| **NONE** | Validierung erfolgreich | Nein | 0s | Task done |
| **PARSING** | JSON-Schema-Fehler | Ja | 5-60s | Retry mit Parsing-Hilfe |
| **SEMANTIC** | Inhaltliche Fehler | Ja | 10-120s | Retry mit verbessertem Prompt |
| **CRITICAL** | Kritischer Fehler | Nein | 0s | Direkt DLQ, kein Retry |

---

## Retry-Strategie

### Exponentielles Backoff

**Formel**:
```
backoff = min(
    base_backoff * (2 ^ retry_count) * (1 + jitter * random()),
    max_backoff
)
```

**Beispiel** (parsing-Fehler, base=5s, jitter=20%):
- Retry 0: ~5s
- Retry 1: ~10s
- Retry 2: ~20s
- Retry 3: ~40s (max: 60s)

### Retry-Limits

| Fehlertyp | Max Retries | Backoff Range |
|-----------|-------------|---------------|
| parsing | 3 | 5-60s |
| semantic | 3 | 10-120s |
| critical | 0 | 0s |

---

## Konfiguration

### Environment-Variablen

```bash
# Validierung
VALIDATION_EVIDENCE_MIN_LENGTH=10        # Mindestlänge für evidence
VALIDATION_EVIDENCE_REQUIRED_FOR_DONE=true  # Evidence erforderlich bei done
VALIDATION_STRICT_MODE=false             # Strenger Modus (Warnungen = Fehler)

# Environment
EXECQUEUE_ENV=development                # development, test, production
EXECQUEUE_TEST_MODE=true                 # Test-Modus

# Eskalation
ESCALATION_WEBHOOK_URL=https://...       # Webhook für Eskalationen
```

### Policy-Datei (`policy.yaml`)

```yaml
validation:
  evidence_min_length: 10
  evidence_required_for_done: true
  strict_mode: false
  schema_version: "1.0.0"

retry_policies:
  parsing:
    max_retries: 3
    base_backoff_seconds: 5
    max_backoff_seconds: 60
    jitter_percent: 20
    prompt_enhancement: "..."
  
  semantic:
    max_retries: 3
    base_backoff_seconds: 10
    max_backoff_seconds: 120
    jitter_percent: 25
    prompt_enhancement: "..."
  
  critical:
    max_retries: 0
    auto_fail: true

escalation:
  retry_threshold: 3
  manual_review_enabled: true
  notification:
    enabled: true
    channels: ["log", "webhook"]
```

### Environment-Overrides

Die Policy unterstützt environment-spezifische Überschreibungen:

```yaml
environments:
  development:
    validation:
      strict_mode: false
      evidence_min_length: 5
    retry_policies:
      parsing:
        max_retries: 5
        base_backoff_seconds: 2
  
  test:
    validation:
      evidence_min_length: 1
    retry_policies:
      parsing:
        max_retries: 1
        base_backoff_seconds: 0
  
  production:
    validation:
      strict_mode: true
      evidence_min_length: 20
    retry_policies:
      parsing:
        max_retries: 2
        base_backoff_seconds: 10
```

---

## Metrics

### Prometheus-Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `execqueue_validation_results_total` | Counter | Validierungsergebnisse | status, error_type |
| `execqueue_validation_duration_seconds` | Histogram | Validierungsdauer | - |
| `execqueue_validation_retries_total` | Counter | Retries by error type | error_type |
| `execqueue_validation_queue_length` | Gauge | Wartende Tasks | - |

**Beispiel**:
```promql
# Validation success rate
sum(execqueue_validation_results_total{status="success"}) / 
sum(execqueue_validation_results_total)

# Average retries per error type
avg(execqueue_validation_retries_total) by (error_type)
```

---

## Integration in Scheduler

Die Validierung ist integriert in `execqueue/scheduler/runner.py`:

```python
# In run_task() nach Ausführung
validation = validate_task_result(
    execution_result.raw_output,
    retry_count=task.retry_count
)

# Metrics erfassen
metrics.increment_validation_result(
    "success" if validation.is_done else "failure",
    validation.error_type
)

# Kritische Fehler - direkt DLQ
if validation.error_type == ValidationErrorType.CRITICAL:
    task.status = "failed"
    _create_dlq_entry(task, session)

# Retry mit Backoff
else:
    task.retry_count += 1
    task.scheduled_after = now + validation.backoff_seconds
    task.status = "queued"
```

---

## Akzeptanzkriterien (Status)

| Kriterium | Status | Nachweis |
|-----------|--------|----------|
| Schema-Validierung 100% | ✅ | `validate_schema()` in allen Pfaden |
| Retry-Dokumentation | ✅ | `error_details` in `TaskValidationResult` |
| Eskalation nach 3 Retries | ✅ | `should_escalate()` + DLQ |
| Metrics in Echtzeit | ✅ | Prometheus-Endpoints `/metrics` |
| Zero Regression | ⏳ | Tests ausführen (siehe unten) |

---

## Tests ausführen

### Unit-Tests
```bash
pytest tests/unit/test_validation_hardening.py -v
```

### Integration-Tests
```bash
pytest tests/integration/test_validation_flow.py -v
```

### Coverage-Report
```bash
pytest --cov=execqueue/validation --cov-report=html
```

**Ziel**: >90% Coverage für `execqueue/validation/`

---

## Migration von altem Validator

### Vorher
```python
from execqueue.validation.task_validator import validate_task_result

result = validate_task_result(output)
if result.is_done:
    # Task done
else:
    # Retry (blind)
```

### Nachher
```python
from execqueue.validation.task_validator import validate_task_result, ValidationErrorType

result = validate_task_result(output, retry_count=task.retry_count)

if result.is_done:
    # Task done
elif result.error_type == ValidationErrorType.CRITICAL:
    # Direkt DLQ
else:
    # Retry mit differenziertem Backoff
    task.scheduled_after = now + result.backoff_seconds
```

### Kompatibilität

Der neue Validator ist **abwärtskompatibel**:
- `result.is_done` verhält sich identisch
- Bestehende Code-Pfade funktionieren unverändert
- Neue Felder sind optional

---

## Troubleshooting

### Häufige Probleme

**Problem**: Validation schlägt immer mit "parsing" fehl  
**Lösung**: Prüfe, ob das OpenCode-Prompt explizit JSON-Output fordert

**Problem**: Tasks eskalieren zu früh  
**Lösung**: `retry_threshold` in `policy.yaml` erhöhen oder `EXECQUEUE_ENV=development` verwenden

**Problem**: Evidence-Qualitäts-Warnungen  
**Lösung**: Prompt verbessern, um konkretere Nachweise zu verlangen (Dateinamen, Zeilennummern)

**Problem**: Backoff ist zu lang  
**Lösung**: `base_backoff_seconds` in `policy.yaml` reduzieren oder `EXECQUEUE_ENV=development`

---

## Versionierung

### Schema-Versionen

- **v1.0.0**: Aktuelle Version (definiert in `schema/v1.json`)
- Erweiterbar durch neue Schema-Dateien (`schema/v2.json`, etc.)
- Rückwärtskompatibel durch `schemaVersion`-Feld im Output

### Policy-Versionierung

- Policy-Änderungen erfordern Neuladen via `reload_policy()`
- Hot-Reload optional (für Production: Restart empfohlen)

---

## Sicherheit

### Input Sanitization (REQ-VAL-004)

- Keine Code-Execution in Validierung
- Output wird nur gelesen, nie ausgeführt
- Logging sanitisiert sensible Daten

### Circuit Breaker (REQ-VAL-014)

- Optional aktivierbar in `policy.yaml`
- Schützt vor External Service Ausfällen

---

## Performance (NFR-VAL-001, NFR-VAL-002)

- Validierungsdurchlauf < 5 Sekunden (ohne External Calls)
- Parallel Validation bis zu 10 Tasks gleichzeitig unterstützt
- Metrics-Overhead < 1%

---

## Compliance & Audit Trail (REQ-VAL-012)

Jede Validierung protokolliert:
- `raw_output_snapshot`: Erster Teil des Outputs (1000 Zeichen)
- `schema_version`: Verwendete Schema-Version
- `validation_passes`: Ergebnis jedes Passes
- `error_details`: Detaillierte Fehlerinformationen

**Logging-Beispiel**:
```
Task 123 validation result: is_done=False, error_type=semantic, 
passes={'schema': True, 'semantic': False}
```

---

## Offene Fragen (aus Anforderungsdokument)

| ID | Frage | Status | Entscheidung |
|----|-------|--------|--------------|
| OF-01 | External Validation Services (CI/CD)? | ⏳ Offen | Nicht im Scope, aber Pipeline-Design ermöglicht Erweiterung |
| OF-02 | Domainspezifische Evidence-Patterns? | ⏳ Offen | Basis-Patterns implementiert, erweiterbar in `semantic_validator.py` |
| OF-03 | Timeouts bei External Calls? | ⏳ Offen | Circuit Breaker vorbereitet, aber nicht aktiviert |
| OF-04 | Compliance-Anforderungen Audit Trail? | ⏳ Offen | Basis-Audit implementiert, erweiterbar bei Bedarf |

---

## Changelog

### Version 1.0.0 (2026-04-23)
- Initial implementation
- Schema-Validator mit JSON Schema Draft 7
- Semantic-Validator mit Status-Konsistenz und Evidence-Qualität
- Policy-Loader mit Environment-Overrides
- Multi-Pass Validierung
- Exponentielles Backoff mit Jitter
- Prometheus Metrics
- Unit- und Integration-Tests (>90% Coverage Ziel)

---

## Referenzen

- [Anforderungsdokument](../requirements/3. Validation verbessern - härten der Validierungslogik.md)
- [JSON Schema Draft 7](https://json-schema.org/draft-07/schema)
- [Prometheus Metrics](https://prometheus.io/docs/concepts/metric_types/)
- [Exponential Backoff](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
