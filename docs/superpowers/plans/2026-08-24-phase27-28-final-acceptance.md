# ChaosAtlas Phase 27-28 Final Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Freeze the existing structured improvement evidence and produce a deterministic final acceptance report for the multi-project one-command closed loop.

**Architecture:** Reuse existing live artifacts, knowledge-card validation, migration isolation audit and dry-run contracts. The final acceptance tool is read-only and reports evidence boundaries; it never enables guarded mode or performs Kubernetes actions.

**Tech Stack:** Python 3, JSON artifacts, pytest.

---

### Task 1: Define final acceptance contract

**Files:**
- Create: `tools/final_acceptance.py`
- Test: `tools/tests/test_final_acceptance.py`

- [x] Write tests for four-project knowledge validation, improvement evidence acceptance, dry-run/runtime boundaries and legacy-default policy.
- [x] Run the tests and verify they fail because the acceptance builder is absent.
- [x] Implement deterministic report generation with explicit `passed`, `blocked` and `not_run` checks.
- [x] Run focused tests and verify they pass.

### Task 2: Wire the report to existing artifacts

**Files:**
- Create: `tools/tests/fixtures/final_acceptance/`
- Modify: `tools/final_acceptance.py`

- [x] Accept project knowledge roots, run summary roots, improvement evidence roots and policy mode as explicit inputs.
- [x] Validate each knowledge root with the flat weakness-card validator and require exact project identity.
- [x] Require at least three accepted project-local cards, no cross-project executable cards, and one valid `improvement_verified` evidence record.
- [x] Require dry-run records to remain synthetic/not_run and policy mode to remain `legacy` unless an explicit guarded gate is supplied.

### Task 3: CLI and documentation

**Files:**
- Modify: `tools/final_acceptance.py`
- Modify: `task_plan.md`
- Modify: `progress.md`

- [x] Add a CLI that writes a JSON report without cluster access.
- [x] Record Phase 27 and Phase 28 acceptance results and the remaining operational boundary.
- [x] Keep the default policy unchanged.

### Task 4: Verification

- [x] Run focused acceptance tests.
- [x] Run the full `tools/tests` suite (`1271 passed`).
- [x] Run `compileall` and `git diff --check`.
- [x] Run the acceptance CLI against the existing four project knowledge roots and improvement evidence.
