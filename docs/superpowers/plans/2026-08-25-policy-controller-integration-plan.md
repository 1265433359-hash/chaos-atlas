# Policy Controller Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已有 policy 选择与停止策略接成 ChaosAtlas batch 的逐轮闭环，并保留 legacy/shadow/guarded 渐进上线。

**Architecture:** 新增轻量 controller facade，复用 `select_candidates_with_policy()` 和 `evaluate_stop()` 的既有算法。`run_live_batch()` 负责冻结候选池、逐轮调用 controller、运行单个 `run_closed_loop()`、读取确定性产物、写 feedback 和更新 state；单次 live CLI 继续拒绝 policy 参数，直到 guarded 验证完成。

**Tech Stack:** Python 3、pytest、JSON/JSONL append-only artifacts。

---

### Task 1: Add controller and feedback contracts

**Files:**
- Create: `tools/policy_controller.py`
- Test: `tools/tests/test_policy_controller.py`

- [ ] Write tests for one-round selection, stop-before-execute, and classification normalization.
- [ ] Run `pytest -q tools/tests/test_policy_controller.py` and confirm RED because the module is absent.
- [ ] Implement a small facade that calls existing gate/stop functions, excludes already attempted candidates, and returns JSON-serializable decisions and feedback eligibility.
- [ ] Run the focused test and confirm GREEN.

### Task 2: Make feedback fail closed for incomplete children

**Files:**
- Modify: `tools/experiment_policy_feedback.py`
- Test: `tools/tests/test_experiment_policy_feedback.py`

- [ ] Add tests proving blocked, method-invalid, cleanup-unverified, and missing-evidence results do not update a candidate posterior.
- [ ] Run the focused tests and confirm RED for the new assertions.
- [ ] Add a deterministic normalization gate before `update_candidate_state()`; preserve existing direct complete-result behavior.
- [ ] Run feedback tests and confirm GREEN.

### Task 3: Replace policy batch selection with a guarded round loop

**Files:**
- Modify: `tools/chaosatlas_batch.py`
- Test: `tools/tests/test_chaosatlas_batch.py`

- [ ] Add tests for two rounds with feedback changing the second candidate, stop preventing a second executor call, and legacy preserving the prefix behavior.
- [ ] Run the batch tests and confirm RED.
- [ ] Implement the loop with per-round child execution, decision/feedback ledgers, state persistence, resume handling, and summary counters. Keep shadow/observe execution on legacy IDs while recording policy decisions.
- [ ] Run batch tests and confirm GREEN.

### Task 4: Verify CLI guardrails and offline rollout modes

**Files:**
- Modify: `tools/tests/test_chaosatlas.py`
- Modify: `tools/tests/test_policy_selection_gate.py`
- Modify: `docs/CHAOSATLAS_CLOSED_LOOP_RUNBOOK.md`

- [ ] Add tests for single-run policy rejection and shadow/guarded mode semantics.
- [ ] Run targeted CLI/gate tests and fix regressions without changing legacy defaults.
- [ ] Document rollout order `shadow -> guarded -> guarded default` and artifact interpretation.

### Task 5: Full verification

- [ ] Run `pytest -q tools/tests/test_policy_controller.py tools/tests/test_experiment_policy_feedback.py tools/tests/test_chaosatlas_batch.py tools/tests/test_policy_selection_gate.py tools/tests/test_chaosatlas.py`.
- [ ] Run the broader policy and batch test subset.
- [ ] Run an offline fake-executor shadow and guarded smoke, inspect JSONL ledgers, and report exact results.
