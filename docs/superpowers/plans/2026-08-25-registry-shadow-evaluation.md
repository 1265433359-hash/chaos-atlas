# Registry Shadow Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a deterministic, read-only quality evaluator and registry shadow report without changing existing candidate execution or live safety behavior.

**Architecture:** Keep `hypothesis_registry.py` as the producer of advisory hypotheses. Add a pure `registry_shadow.py` consumer that validates the registry against the candidate pool and compares legacy ordering with a registry-derived runtime-only ordering. Wire it into `chaosatlas run` behind `--registry-shadow` as two non-stage advisory artifacts.

**Tech Stack:** Python 3, existing JSON artifact envelopes, pytest, canonical SHA-256 hashing.

---

### Task 1: Define evaluator and shadow contracts with failing tests

**Files:**
- Create: `tools/registry_shadow.py`
- Create: `tools/tests/test_registry_shadow.py`

- [x] **Step 1: Add fixtures and tests for a healthy registry.**

The fixture must contain all five kinds, two runtime candidates, one static architecture hypothesis, and a candidate pool with a legacy order. Assert that `evaluate_registry_quality` returns `status="passed"`, all required kinds are present, the runtime intersection is exact, and `build_registry_shadow` returns only runtime candidate IDs.

- [x] **Step 2: Add tests for fail-closed quality errors.**

Cover a missing required field, duplicate `hypothesis_id`, unknown runtime `candidate_id`, non-advisory claim scope, and a static hypothesis incorrectly marked executable. Assert structured `status="failed"` and error codes; do not expect exceptions.

- [x] **Step 3: Add tests for deterministic shadow differences and side-effect flags.**

Pass a legacy order `[candidate-a, candidate-b]` and registry runtime priorities that reverse it. Assert `selection_changed=true`, stable `common_candidate_ids`, `legacy_only_candidate_ids`, `registry_only_candidate_ids`, and all mutation/policy/knowledge flags are false. Repeat the call and assert equality.

- [x] **Step 4: Run the focused tests and verify RED.**

Run:

```powershell
python -m pytest --basetemp .tmp-pytest-registry-shadow-red tools/tests/test_registry_shadow.py -q
```

Expected: collection or import failure because `tools.registry_shadow` is not implemented.

### Task 2: Implement deterministic quality evaluation and shadow ordering

**Files:**
- Modify: `tools/registry_shadow.py`
- Test: `tools/tests/test_registry_shadow.py`

- [x] **Step 1: Implement canonical helpers and structured error reporting.**

Use sorted-key JSON SHA-256. Return `{schema_version, status, errors, checks, input_sha256, claim_scope}`. Errors are objects with stable `code`, `path`, and `message` fields.

- [x] **Step 2: Implement `evaluate_registry_quality`.**

Require the five kinds and required fields `hypothesis_id`, `kind`, `target`, `mechanism`, `preconditions`, `expected_observations`, `falsifiers`, `required_evidence`, `priority_score`, `execution_eligible`, and `claim_scope`. Verify unique IDs, advisory scope, runtime IDs exist in the candidate pool, non-runtime entries are not executable, and report `execution_eligible_count` independently from `execution_budget`.

- [x] **Step 3: Implement `build_registry_shadow`.**

Use the existing candidate order as legacy order. Build the registry order from runtime hypotheses sorted by descending `priority_score`, then `hypothesis_id`; ignore all static kinds. Compare top-k IDs and emit the required side-effect flags. Return `claim_scope="advisory"` even when quality is failed.

- [x] **Step 4: Run focused tests and verify GREEN.**

Run the same command with `-q`; expected all tests pass.

### Task 3: Wire optional reports into the unified offline run

**Files:**
- Modify: `tools/chaosatlas.py`
- Modify: `tools/tests/test_chaosatlas.py`

- [x] **Step 1: Add the `registry_shadow` function parameter and CLI flag.**

Add `registry_shadow: bool = False` to `run_closed_loop` and `run.add_argument("--registry-shadow", action="store_true")`. Keep the default path byte-compatible in stage order and output set.

- [x] **Step 2: Generate reports after the existing portrait and registry artifacts.**

When enabled, load the advisory payloads and candidate/hypothesis payloads, call the two pure functions, and write `registry_quality_report.json` and `registry_policy_shadow.json` using the existing advisory envelope writer. Pass the execution budget from `execution_contract.budget.max_candidates`. Never pass these reports into candidate selection or live execution.

- [x] **Step 3: Add CLI propagation and regression assertions.**

Propagate `args.registry_shadow` to `run_closed_loop`. Assert default runs do not create the two files; enabled dry-runs create both with advisory scope, no side-effect flags, and a report that has more than one hypothesis but a budget of one.

- [x] **Step 4: Run the focused orchestrator tests.**

Run:

```powershell
python -m pytest --basetemp .tmp-pytest-registry-shadow-orchestrator tools/tests/test_registry_shadow.py tools/tests/test_chaosatlas.py tools/tests/test_chaosatlas_batch.py -q
```

Expected: all tests pass and default behavior remains unchanged.

### Task 4: Fresh two-project verification and documentation

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [x] **Step 1: Run fresh Sock Shop and Online Boutique shadow dry-runs.**

Use separate non-empty output directories and `--registry-shadow`; assert both return `dry_run_ready`, create both reports, and have `mutation_executed=false`, `policy_state_updated=false`, and `formal_knowledge_written=false`.

- [x] **Step 2: Repeat one run and compare deterministic fields.**

Compare `input_sha256`, candidate order, `selection_changed`, and side-effect flags between two fresh runs with the same profile and seed.

- [x] **Step 3: Run compileall and record the boundary.**

Run `python -m compileall -q tools/registry_shadow.py tools/chaosatlas.py` and record that registry shadow is an acceptance/evaluation layer only; guarded policy integration remains a later phase.
