# Registry Policy Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Feed validated runtime hypothesis priority into policy selection with bounded scoring, explicit fallback, and shadow/guarded audit artifacts.

**Architecture:** Add a pure `registry_policy_signal.py` adapter that validates the advisory registry and emits a capped candidate bonus map. Extend existing deterministic policy scoring to consume that map only when supplied. Have `run_live_batch` build the signal from its frozen discovery inputs, preserve legacy execution in shadow mode, and require the signal quality/hash gates before guarded execution.

**Tech Stack:** Python 3, existing policy gate/controller, JSON/JSONL artifacts, pytest.

---

### Task 1: Build the validated bounded signal adapter

**Files:**
- Create: `tools/registry_policy_signal.py`
- Create: `tools/tests/test_registry_policy_signal.py`

- [x] Write tests for accepted runtime-only entries, bounded normalized bonuses, static hypothesis exclusion, missing/invalid quality fallback, unknown candidate rejection, and deterministic hashes.
- [x] Run the focused tests and confirm RED because the adapter is absent.
- [x] Implement `build_registry_policy_signal(registry, quality_report, candidate_space, bonus_cap=0.25)` returning a structured status, allowed IDs, `priority_bonus`, `input_sha256`, and fallback reason without raising for malformed input.
- [x] Run focused tests and confirm GREEN.

### Task 2: Add registry bonus to deterministic policy scoring

**Files:**
- Modify: `tools/experiment_policy.py`
- Test: `tools/tests/test_experiment_policy.py`

- [x] Add tests proving no context preserves existing values, a valid signal adds at most the cap, and unknown/negative/non-finite bonuses contribute zero.
- [x] Implement only an optional `registry_priority_bonus` component in `score_experiment`; do not alter posterior, stop policy, or candidate eligibility.
- [x] Run existing policy tests plus the new tests.

### Task 3: Integrate signal into live batch modes and ledgers

**Files:**
- Modify: `tools/chaosatlas_batch.py`
- Modify: `tools/policy_controller.py`
- Modify: `tools/tests/test_chaosatlas_batch.py`
- Modify: `tools/tests/test_policy_controller.py`

- [x] Add a discovery helper that builds portrait/registry/quality from the batch adapter's inventory, detection, and candidate space, then filters the signal to the Oracle-scoped frozen pool.
- [x] Add tests for shadow preserving legacy execution while recording registry selection, guarded executing only the registry-selected allow-listed candidate, and invalid signal falling back to legacy with a reason.
- [x] Persist `registry-policy-input.json` and append `registry-policy-decisions.jsonl` for shadow/guarded modes; include signal hash, selected IDs, fallback reason, and stop result.
- [x] Pass the signal context into `PolicyController` only for shadow/guarded/default; keep legacy path unchanged.
- [x] Run batch/controller tests and verify no executor call occurs for stop or invalid guarded gates.

### Task 4: Offline rollout verification and documentation

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`
- Modify: `docs/CHAOSATLAS_CLOSED_LOOP_RUNBOOK.md`

- [x] Run a fake-executor shadow and guarded smoke using a two-candidate fixture; inspect both policy ledgers and registry input artifact.
- [x] Run Sock Shop and Online Boutique fresh offline shadow dry-runs; verify deterministic signal hashes, legacy execution in shadow, and no formal knowledge or Kubernetes writes.
- [x] Run compileall and focused policy/batch/orchestrator tests.
- [x] Record that guarded real canary approval remains a separate gate and legacy remains default.
