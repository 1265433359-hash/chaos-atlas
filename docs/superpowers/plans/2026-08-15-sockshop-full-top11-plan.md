# Sock Shop Full Top 11 Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze and evaluate the actual highest-confidence 11 Full hypotheses without filtering by evidence availability or replacing blocked candidates.

**Architecture:** A pure selection tool reads the existing immutable overlap audit, reconstructs all Full family representatives, sorts only by frozen confidence, and writes a hash-pinned Top 11 manifest. Existing applicability and Sock Shop runners are reused after adding an explicit HTTP target-port blocker; a separate batch tool reuses only strict valid evidence and executes only missing ready candidates.

**Tech Stack:** Python 3.12, pytest, PyYAML, kubectl, existing Sock Shop two-arm runner.

---

### Task 1: Freeze the actual Full Top 11

**Files:**
- Create: `tools/build_sock_shop_full_top11.py`
- Create: `tools/tests/test_build_sock_shop_full_top11.py`

- [ ] Write a failing test that supplies more than 11 Full representatives and proves selection ignores evidence and gate fields, sorts by confidence, keeps deterministic tie ordering, refuses non-empty output, and writes pending/no-KB metadata.
- [ ] Run `python -m pytest tools/tests/test_build_sock_shop_full_top11.py -q` and verify the import failure.
- [ ] Implement pure reconstruction and `(-confidence, source_order, mutation_instance_key)` sorting, source/mutation SHA verification, manifest output and SHA-256 sidecar.
- [ ] Run the new test and confirm all assertions pass.

### Task 2: Make target-port mismatch an explicit blocker

**Files:**
- Modify: `tools/runtime_applicability_gate.py`
- Modify: `tools/tests/test_runtime_applicability_gate.py`

- [ ] Add a failing HTTPChaos regression where the selector matches a Pod exposing 3306 but the mutation requests port 80; assert `target_port_missing` appears in errors even when another injector blocker also exists.
- [ ] Run the targeted test and verify it fails on the missing explicit error.
- [ ] Add `target_port_missing` to gate errors and block injection whenever HTTPChaos specifies a port not exposed by any selected ready Pod.
- [ ] Run the targeted and full applicability tests.

### Task 3: Gate all 11 without replacement

**Files:**
- Create: `tools/gate_sock_shop_full_top11.py`
- Create: `tools/tests/test_gate_sock_shop_full_top11.py`

- [ ] Add tests proving every manifest entry is represented exactly once, blocked entries remain in rank order, no replacement occurs, server-side dry-run output is recorded, and manifest SHA must match.
- [ ] Implement aggregate gate orchestration around `runtime_applicability_gate.py` and `kubectl apply --dry-run=server`.
- [ ] Run unit tests, then execute against Minikube into `chaosatlas_sockshop_full_top11_2026-08-15-r1/`.
- [ ] Stop before injection if any unexpected lifecycle or global residual condition exists.

### Task 4: Resolve existing strict evidence

**Files:**
- Create: `tools/build_sock_shop_full_top11_execution_plan.py`
- Create: `tools/tests/test_build_sock_shop_full_top11_execution_plan.py`

- [ ] Test that only two valid reports with the same executable mutation satisfy reuse, blocked candidates never become runtime units, and missing ready candidates receive exactly two fresh units.
- [ ] Implement evidence validation using report, mutation and diagnostics SHA-256 checks.
- [ ] Write a hash-pinned execution plan that labels each candidate `reused_historical`, `fresh_required`, or `blocked`.

### Task 5: Execute missing ready candidates

**Files:**
- Create: `tools/run_sock_shop_full_top11_batch.py`
- Create: `tools/tests/test_run_sock_shop_full_top11_batch.py`

- [ ] Test non-empty output refusal/resume, stop-on-failure, two replicates per fresh candidate, and no command generation for reused or blocked candidates.
- [ ] Execute fresh units serially with the existing runner and recovery timeout 240 seconds.
- [ ] After every report verify recovery, cleanup, global absence and washout; stop immediately on failure.

### Task 6: Review and compare

**Files:**
- Create: `tools/review_sock_shop_full_top11.py`
- Create: `tools/tests/test_review_sock_shop_full_top11.py`
- Create: `artifacts/experiments/chaosatlas_sockshop_full_top11_review_2026-08-15-r1/`

- [ ] Test executable-rate, stable/unstable/no-impact classification and blocked denominator separation.
- [ ] Rehash all reports and diagnostics and generate Chinese JSON/Markdown review artifacts.
- [ ] Recompute overlap with Ablation by executable mutation identity before any cross-arm claim.
- [ ] Run focused regression, `git diff --check`, secret scan and final Minikube/global residual checks.
- [ ] Keep human review pending and do not update the knowledge base.
