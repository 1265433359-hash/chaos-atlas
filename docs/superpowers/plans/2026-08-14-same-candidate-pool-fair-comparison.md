# Same Candidate Pool Fair Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a frozen, result-free candidate pool for Online Boutique, OpenTelemetry Demo, and Sock Shop, then prepare method inputs for fair same-pool selection.

**Architecture:** Add a small offline builder that emits candidate records, Chaos Mesh YAML, SHA-256 manifest, and method-facing selection inputs. Runtime execution remains a later gate and reuses the existing project runners.

**Tech Stack:** Python, JSON, YAML, pytest, existing Chaos Mesh runner contracts.

---

### Task 1: Candidate Pool Builder

**Files:**
- Create: `tools/build_same_pool_fair_inputs.py`
- Create: `tools/tests/test_build_same_pool_fair_inputs.py`

- [ ] Write tests for non-empty output guard, namespace-local YAML, result-label exclusion, and deterministic hashes.
- [ ] Implement candidate generation from frozen runner target sets.
- [ ] Run focused tests with repository-local pytest basetemp.

### Task 2: Generate Frozen Pool

**Files:**
- Create output under `artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r1/`

- [ ] Run the builder into a fresh non-empty-safe directory.
- [ ] Verify each project has candidates and YAML SHA-256 records.
- [ ] Run server-side dry-run for generated YAML only after namespace health is checked.

### Task 3: Method Selection Inputs

**Files:**
- Modify: `tools/build_same_pool_fair_inputs.py`
- Test: `tools/tests/test_build_same_pool_fair_inputs.py`

- [ ] Emit method-facing inputs for `ChaosAtlas-full`, `ChaosAtlas-ablation`, and `ChaosEater-adapter`.
- [ ] Verify all methods receive byte-identical candidate pools per project/seed.
- [ ] Verify only `ChaosAtlas-full` receives the allowed knowledge view.

### Task 4: Runtime Handoff

**Files:**
- Create: `artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r1/reports/freeze-review.md`

- [ ] Summarize pool size, hashes, excluded labels, and current gate status.
- [ ] Keep `human_review=pending` and `knowledge_base_updated=false`.
- [ ] Do not start runtime until dry-run and user-approved method selection are complete.

