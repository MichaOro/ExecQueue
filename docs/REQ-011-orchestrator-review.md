# 📋 REQ‑011 Orchestrator Execution Preparation – In‑Depth Review
*Prepared for inclusion as `docs/REQ-011-orchestrator-review.md`*

---

## 1️⃣ Overview

REQ‑011 implements the preparation phase of the ExecQueue orchestrator. Its responsibility ends once a `PreparedExecutionContext` (PE‑Context) is ready for hand‑off to the later *execution* phase.

| # | Module | Primary Concern |
|---|--------|-----------------|
| 1 | `candidate_discovery.py` | Load executable backlog tasks from DB, deterministic ordering, dependency filtering |
| 2 | `classification.py` | Classify tasks (read‑only / write, parallel / sequential) and build a safe **BatchPlan** |
| 3 | `locking.py` | Atomic `backlog → queued` transition with concurrency guarantees |
| 4 | `git_context.py` | Prepare isolated Git branch & work‑tree for write‑tasks |
| 5 | `context_contract.py` | Build and validate the `PreparedExecutionContext` DTO |
| 6 | `main.py` | High‑level orchestration |
| 7 | `recovery.py` | Recover stale or conflicted queued tasks |
| 8 | `observability.py` | Structured logging & negative‑assertion tests |
| 9 | `models.py` | DTO & enum definitions |

---

## 2️⃣ Component‑by‑Component Quality Assessment

### 2.1 `candidate_discovery.py`

| Rating | 4 |
|--------|---|
| **Strengths** | Clear doc‑string, single query with proper filters, deterministic ordering, batch limit. |
| **Weaknesses** | Placeholder dependency filtering; `count_pending` returns only `0/1`. |
| **Improvements** | Replace placeholder filter with real JSON check or a separate `DependencyResolver`; make `count_pending` return a true count; consider returning a tiny `@dataclass` for candidates. |
| **Key Lines** | 66‑100 (query), 112‑127 (`count_pending`). |

---

### 2.2 `classification.py`

| Rating | 5 |
|--------|---|
| **Strengths** | Pure functional, no side‑effects, comprehensive reason strings, uses `@dataclass`. |
| **Weaknesses** | `parallel_mode` is a free‑form string; conflict‑key relies only on task number. |
| **Improvements** | Introduce a `ParallelMode` enum (or `Literal`); generate conflict keys using a hash of `task_id` for guaranteed uniqueness. |
| **Key Lines** | 54‑118 (`classify`), 120‑145 (`classify_batch`). |

---

### 2.3 `locking.py`

| Rating | 5 |
|--------|---|
| **Strengths** | True atomic `UPDATE … WHERE status='backlog'`; validates `rowcount`; clean `LockResult` DTO; batch & single‑task APIs. |
| **Weaknesses** | `release_lock` silently does nothing if task isn’t queued – add a short doc‑string. |
| **Improvements** | Document “no‑op if not queued” semantics; optionally expose a `max_retries` parameter for future back‑off logic. |
| **Key Lines** | 84‑156 (`lock_tasks`), 170‑242 (`lock_single_task`), 256‑294 (`release_lock`). |

---

### 2.4 `git_context.py`

| Rating | 4 |
|--------|---|
| **Strengths** | Safety invariants, branch‑name validation, reuse of clean work‑trees, unified error handling via `PreparationError`. |
| **Weaknesses** | Synchronous `subprocess.run`; placeholder `task_id=UUID(int=0)` for command‑level errors; folder creation in `__init__`. |
| **Improvements** | Wrap subprocess calls in an injectable `GitRunner` interface for mocking; make the runner async‑compatible; pass real `task_id` into `_run_git_command`. |
| **Key Lines** | 76‑127 (`_run_git_command`), 163‑181 (`_generate_branch_name`), 245‑350 (`prepare_context`). |

---

### 2.5 `context_contract.py`

| Rating | 5 |
|--------|---|
| **Strengths** | Builder pattern, explicit validation rules, versioned DTO. |
| **Weaknesses** | None obvious. |
| **Improvements** | Add a `to_dict()` helper for easy JSON logging. |
| **Key Lines** | `build_context`, `validate_context`. |

---

### 2.6 `main.py`

| Rating | 4 |
|--------|---|
| **Strengths** | Clear high‑level flow, consolidated `PreparationResult`. |
| **Weaknesses** | `run_preparation_cycle` is ~150 LOC; mixes DB commits with potentially long Git calls; duplicated log messages. |
| **Improvements** | Split into private helpers (`_discover`, `_classify`, `_plan`, `_lock`, `_prepare_context`); consider a single commit after the whole batch; explore async orchestration for Git steps. |
| **Key Lines** | 99‑188 (`run_preparation_cycle`), 189‑322 (`_prepare_task_context`). |

---

### 2.7 `recovery.py`

| Rating | 5 |
|--------|---|
| **Strengths** | Explicit recovery matrix, classification of recoverable vs non‑recoverable errors. |
| **Weaknesses** | No dedicated unit tests for the matrix. |
| **Improvements** | Add a small test suite that injects mock `PreparationError`s and asserts correct status transitions. |
| **Key Lines** | Error handling in `_prepare_task_context` (285‑292). |

---

### 2.8 `observability.py`

| Rating | 5 |
|--------|---|
| **Strengths** | Structured event names, comprehensive negative‑assertion E2E tests. |
| **Weaknesses** | No runtime schema validation of log payloads. |
| **Improvements** | Implement a `log_event(name, **payload)` wrapper that validates required fields (e.g., via pydantic). |
| **Key Lines** | Event definitions and logging calls in each component. |

---

### 2.9 `models.py`

| Rating | 5 |
|--------|---|
| **Strengths** | String‑based enums (DB‑friendly), immutable DTOs, full type hints. |
| **Weaknesses** | None significant. |
| **Improvements** | Add a custom `__repr__` that truncates large `details` dicts for cleaner logs. |
| **Key Lines** | Enum definitions (59‑75) and DTOs later in the file. |

---

## 3️⃣ Overall Assessment

| Criterion | Score (1‑5) | Comment |
|-----------|-------------|---------|
| Correctness | 5 | State transitions follow the documented matrix; no forbidden transitions. |
| Readability / Documentation | 4 | Good doc‑strings; a few helpers could use more inline comments. |
| Type Safety | 4 | Strong typing overall; a few free‑form strings could be tightened. |
| Error Handling | 5 | Consistent `PreparationError` hierarchy; explicit recovery paths. |
| Test Coverage | 3 | Only negative E2E tests; unit‑test gaps in classification, batching, recovery. |
| Performance / Scalability | 4 | Batch limits & single‑query discovery are efficient; synchronous Git calls may block under load. |
| Architectural Alignment | 5 | Strict adherence to the `execqueue/orchestrator/` package layout; no cross‑package leakage. |
| Maintainability | 4 | Clear separation of concerns, but the monolithic orchestrator method hampers future changes. |

**Overall Grade:** **4.2 / 5** – a solid foundation with clear improvement opportunities.

---

## 4️⃣ Recommendations – Prioritized Action Plan

| Priority | Recommendation | Rationale | Approx. Effort |
|----------|----------------|-----------|----------------|
| 🟢 High | Add **unit‑tests** for core pure functions (`CandidateDiscovery.find_candidates` (mock DB), `TaskClassifier.classify`, `BatchPlanner.create_batch_plan`, `Recovery` logic). | Improves regression safety; existing coverage is only E2E negative tests. | ~2 days |
| 🟢 High | Refactor `Orchestrator.run_preparation_cycle` into smaller private methods (`_discover`, `_classify`, `_plan`, `_lock`, `_prepare_context`). | Reduces method size, isolates DB vs Git, easier mocking. | ~1 day |
| 🟡 Medium | Introduce a **`ParallelMode` enum** (or `Literal`) and replace free‑form strings in `TaskClassifier`. | Provides static guarantees, avoids typo‑induced bugs. | < ½ day |
| 🟡 Medium | Replace the **placeholder dependency filtering** in `CandidateDiscovery` with a real JSON check or a pluggable `DependencyResolver`. | Prevents hidden blockers from sneaking in. | 1‑2 days |
| 🟡 Medium | Make **Git subprocess calls injectable** via a `GitRunner` interface (or async wrapper). | Improves testability, enables future async execution. | ~1 day |
| 🟡 Medium | Provide an **async variant** for Git preparation (`async_prepare_context`). | Non‑blocking when many write‑tasks are prepared in parallel. | 2‑3 days |
| 🔴 Low | Enhance **`count_pending`** to return a true integer count. | Minor monitoring improvement. | < ½ day |
| 🔴 Low | Add a **`log_event`** helper with runtime schema validation (pydantic). | Guarantees log payload completeness. | ~1 day |
| 🔴 Low | Document the **conflict‑key generation** algorithm in the design docs (README or architectural diagram). | Improves developer onboarding. | < ½ day |

*All suggested changes respect the architecture‑ and interface‑rules: they extend existing files, only introduce new modules when reusable (e.g., `GitRunner`, `DependencyResolver`), and avoid unnecessary helper‑only utilities.*

---

## 5️⃣ Next Steps

1. **Create a new test module** (`tests/test_candidate_discovery.py`, `tests/test_classification.py`, …) with fixtures that mock a SQLAlchemy session.
2. **Refactor `Orchestrator`** as described; update imports accordingly.
3. **Introduce a `ParallelMode` enum** in `models.py` and adjust `TaskClassifier`.
4. **Implement a thin `GitRunner` abstraction** (interface + default `SubprocessGitRunner`) and inject it into `GitContextPreparer`.
5. **Run the full test suite** (`pytest -q`) after each change to ensure no regressions.

When you are ready to apply any of these changes, let me know which subset you would like to start with and I can generate the concrete patches.
