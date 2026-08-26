# ChaosAtlas Productization Completion Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with test-first changes and verification after each task.

**Goal:** Make the existing deterministic ChaosAtlas single and batch runners auditable, fail-closed, and resumable without changing candidate ranking or stop policy.

**Architecture:** Keep `run_closed_loop` as the authoritative child-run pipeline. Add a small batch state/manifest layer in `chaosatlas_batch.py`; each child remains isolated and emits normal single-run artifacts. Aggregate only deterministic child artifacts and reject resume when immutable inputs differ.

**Tech Stack:** Python 3, argparse, JSON artifacts, pytest.

---

### Task 1: Define batch state and aggregate contract

**Files:**
- Modify: `tools/chaosatlas_batch.py`
- Test: `tools/tests/test_chaosatlas_batch.py` (create)

- [x] **Step 1: Write failing tests** for immutable manifest creation, child state transitions, and aggregate counts for completed, blocked, failed, and cleanup-failed children.
- [x] **Step 2: Run the focused tests and verify they fail** because the state/manifest helpers do not exist.
- [x] **Step 3: Implement minimal helpers**: `build_batch_manifest`, `append_batch_state`, and `summarize_batch_results`; keep JSON schemas versioned and deterministic.
- [x] **Step 4: Run the focused tests and verify they pass.**

### Task 2: Persist batch manifest and state during execution

**Files:**
- Modify: `tools/chaosatlas_batch.py`
- Test: `tools/tests/test_chaosatlas_batch.py`

- [x] **Step 1: Write failing tests** proving the manifest is written before child execution and state is updated after every child, including exceptions.
- [x] **Step 2: Run the tests and verify the expected failure.**
- [x] **Step 3: Integrate manifest/state writes** into `run_live_batch`; preserve current child output paths and live approval gates.
- [x] **Step 4: Run focused batch tests and verify all pass.**

### Task 3: Add safe resume/reconcile validation

**Files:**
- Modify: `tools/chaosatlas_batch.py`
- Modify: `tools/chaosatlas.py` only if shared input-snapshot validation is required
- Test: `tools/tests/test_chaosatlas_batch.py`

- [x] **Step 1: Write failing tests** for rejecting changed profile hash, kube context, namespace, candidate-space hash, and live runs that crossed the mutation boundary.
- [x] **Step 2: Run the tests and verify they fail for the missing validation.**
- [x] **Step 3: Add `resume` support** with immutable manifest validation and skip only children already at a verified terminal state; refuse unsafe live resume.
- [x] **Step 4: Run focused tests and verify all pass.**

### Task 4: Expose the stable command contract and documentation

**Files:**
- Modify: `tools/chaosatlas.py`
- Modify: `docs/CHAOSATLAS_CLOSED_LOOP_RUNBOOK.md`
- Test: `tools/tests/test_chaosatlas.py`

- [x] **Step 1: Write failing CLI tests** for batch resume flags and deterministic summary paths.
- [x] **Step 2: Run the tests and verify they fail.**
- [x] **Step 3: Add only the required CLI wiring and update the runbook** with dry-run, live approval, context pinning, batch outputs, and resume restrictions.
- [x] **Step 4: Run CLI-focused tests and verify all pass.**

### Task 5: Full verification and handoff

**Files:**
- No production changes unless verification exposes a regression.

- [x] **Step 1: Run the complete focused ChaosAtlas/RCA/batch suite.**
- [x] **Step 2: Run `python -m compileall tools` and `git diff --check`.**
- [x] **Step 3: Run Sock Shop context-pinned dry-run; run live only with the existing explicit approval and cleanup gates.**
- [x] **Step 4: Record artifact paths, statuses, and any environment limitations in the final handoff.**
