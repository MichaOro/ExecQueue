# Implementation Test Strategy

## TL;DR
Tests are classified along two dimensions:
1. **System Criticality** (impact on system stability)
2. **Business Logic Coverage** (importance for correct behavior)

A combined score determines prioritization: **Critical, High, Medium, Low**

---

## 1. Objectives

- Ensure **functional correctness**
- Ensure **system stability**
- Minimize **test gaps (delta)**
- Balance **speed vs. quality**
- Enable **LLM + human collaboration**

---

## 2. Test Types

### Unit Tests
- Isolated logic validation
- Use mocks/stubs
- Fast, deterministic
- Example:
  - DB connection function (mocked)

### Integration Tests
- Real component interaction
- No mocks for critical paths
- Validate infrastructure & config
- Example:
  - Real DB connection
  - Telegram API interaction

---

## 3. Scoring Model

Use a simple additive 1–3 scoring model across two dimensions:

### 1. System Criticality

Defines how critical a component or feature is for the overall system stability.

| Score | Description                          |
|------:|--------------------------------------|
| 1     | Core system dependency (DB, API)     |
| 2     | Important feature                    |
| 3     | Nice-to-have / edge case             |

---

### 2. Business Logic Coverage

Defines how important it is to explicitly validate this behavior via tests.

| Score | Description                          |
|------:|--------------------------------------|
| 1     | Must be explicitly tested            |
| 2     | Should be tested                     |
| 3     | Implicitly covered / redundant       |

---

### 4. Priority Calculation

```
Priority Score = Criticality + Coverage
```
### Priority Mapping

| Score | Priority  |
|-------|----------|
| 2     | Critical |
| 3     | High     |
| 4     | Medium   |
| 5–6   | Low      |

---

## 5. Examples

### Database Connection

- Criticality: **1**
- Coverage: **1**

→ Score = 2.0 → **Critical**

---

### `/health` Command Exists

- Criticality: **2**
- Coverage: **3**

→ Score = 5 → **Low**

Reasoning:
The explicit existence test has low standalone value because the `/health` result validation test implicitly verifies that the command exists and can be executed.

### `/health` Command Result Validation

- Criticality: **2**
- Coverage: **1**

→ Score = 3 → **High**

Reasoning:
The `/health` result validation verifies that the command is executable and returns the expected health information. It provides direct assurance for operational readiness and implicitly covers command existence.

---

## 6. Folder Structure

```
/tests
  /unit
  /integration
  /clusters
```

---

## 7. Test Clustering

Tests must be grouped into clusters:

- `critical`
- `high`
- `medium`
- `low`

Each test MUST include metadata:

```yaml
priority: critical
type: integration
requirement: telegram_start
```

---

## 8. Requirement-Based Documentation

For each feature / requirement:

- Create or update a document:

```
/docs/tests/<requirement>.md
```

### Content:

- List of all related tests
- Classification (unit/integration)
- Priority cluster
- Coverage explanation

---

## 9. LLM Workflow Integration

### Implementation Phase
- Minimal prompt
- Focus on feature delivery

### Validation Phase
- Inject Test Strategy
- Enforce:
  - Test creation/update
  - Correct classification
  - Documentation update

---

## 10. Guardrails

- No integration test → FAIL for critical paths
- Mock-only DB tests → NOT sufficient
- Redundant tests → allowed if low maintenance
- Every requirement → must map to tests

---

## 11. Best Practices

- Prefer **clarity over quantity**
- Allow **controlled redundancy**
- Always include **at least one real integration test** for critical components
- Keep tests **deterministic**
- Avoid **over-mocking critical infrastructure**

---

## 12. Summary

This strategy ensures:
- Scalable test architecture
- Consistent quality across LLM + human work
- Controlled growth of test suites
- Clear prioritization based on real system risk
