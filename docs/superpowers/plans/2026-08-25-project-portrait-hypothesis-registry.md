# Project Portrait and Hypothesis Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate an auditable project portrait and a broad, evidence-bounded hypothesis registry before the existing policy selects a small number of live experiments.

**Architecture:** Keep the existing onboarding, inventory, deployment detection, mapping, retrieval, and live safety gates unchanged. Add a side-effect-free builder that derives `project_portrait.json` and `hypothesis_registry.json` from those verified inputs; runtime candidates remain the only immediately executable hypotheses, while architecture, configuration, dependency, and defense hypotheses explicitly record evidence or retest prerequisites.

**Tech Stack:** Python 3, existing ChaosAtlas JSON artifacts, pytest, deterministic hashing.

---

### Task 1: Define portrait and registry contracts with failing tests

**Files:**
- Create: `tools/hypothesis_registry.py`
- Test: `tools/tests/test_hypothesis_registry.py`

- [x] **Step 1: Write tests for deterministic portrait normalization and hypothesis categories.**

```python
def test_registry_contains_runtime_architecture_configuration_dependency_and_defense_hypotheses():
    portrait = build_project_portrait(INVENTORY, DETECTION, CANDIDATE_SPACE, cards=[CARD])
    registry = build_hypothesis_registry(
        INVENTORY, DETECTION, CANDIDATE_SPACE, advisory=ADVISORY, cards=[CARD]
    )
    assert portrait["schema_version"] == "chaosatlas-project-portrait-v1"
    assert {item["kind"] for item in registry["hypotheses"]} == {
        "architecture", "configuration", "dependency", "runtime", "defense"
    }
    assert registry["counts"]["runtime"] == 2
    assert registry["execution_eligible_count"] == 2

def test_registry_marks_unknown_pdb_as_evidence_required_not_absent():
    registry = build_hypothesis_registry(INVENTORY, DETECTION, CANDIDATE_SPACE, advisory=ADVISORY, cards=[])
    pdb = next(item for item in registry["hypotheses"] if item["mechanism"] == "pdb_coverage_needs_verification")
    assert pdb["execution_eligible"] is False
    assert "pdb" in pdb["required_evidence"]
    assert "weakness_status" not in pdb

def test_registry_is_stable_and_deduplicated():
    first = build_hypothesis_registry(INVENTORY, DETECTION, CANDIDATE_SPACE, advisory=ADVISORY, cards=[])
    second = build_hypothesis_registry(INVENTORY, DETECTION, CANDIDATE_SPACE, advisory=ADVISORY, cards=[])
    assert first == second
    ids = [item["hypothesis_id"] for item in first["hypotheses"]]
    assert len(ids) == len(set(ids))
```

- [x] **Step 2: Run the focused tests and verify the expected missing-symbol failure.**

Run: `python -m pytest tools/tests/test_hypothesis_registry.py -q`

Expected: FAIL because `tools.hypothesis_registry` does not yet expose the two builders.

### Task 2: Implement deterministic project portrait and hypothesis registry

**Files:**
- Modify: `tools/hypothesis_registry.py`
- Test: `tools/tests/test_hypothesis_registry.py`

- [x] **Step 1: Implement canonical hashing, safe deployment normalization, and portrait construction.**

The portrait must include project identity, namespace, deployments, services, dependency edges, business oracles, candidate-family coverage, knowledge-card ids, and a canonical `input_sha256`. It must only copy the already sanitized inventory/detection inputs.

- [x] **Step 2: Implement category builders.**

Generate:

- `runtime`: one executable hypothesis per mapped candidate;
- `architecture`: singleton availability hypotheses for deployments with one desired replica;
- `configuration`: missing/unknown PDB, resource-limit, and readiness evidence hypotheses only when the input supports the observation;
- `dependency`: one service-edge availability hypothesis per declared dependency;
- `defense`: one redundancy-preservation hypothesis paired with each singleton architecture hypothesis.

Every item must contain `hypothesis_id`, `kind`, `target`, `mechanism`, `preconditions`, `expected_observations`, `falsifiers`, `required_evidence`, `priority_score`, `execution_eligible`, and `claim_scope: advisory`. No item may contain runtime verdict or knowledge-promotion fields.

- [x] **Step 3: Implement stable sort, deduplication, counts, and coverage summary.**

Sort by descending priority, then kind, target, and hypothesis id. Return `hypothesis_count`, per-kind counts, `execution_eligible_count`, `candidate_ids`, and `coverage` so policy selection can consume the registry later without changing current policy behavior.

- [x] **Step 4: Run the focused tests and verify GREEN.**

Run: `python -m pytest tools/tests/test_hypothesis_registry.py -q`

Expected: all registry tests pass.

### Task 3: Emit portrait and registry artifacts from the closed loop

**Files:**
- Modify: `tools/chaosatlas.py`
- Modify: `tools/tests/test_chaosatlas.py`

- [x] **Step 1: Add artifact writers after mapping/retrieval and before hypothesis execution.**

Write `project_portrait.json` and `hypothesis_registry.json` as advisory envelopes with payload hashes. On resume, read existing artifacts instead of recomputing from a changed input. Do not add a runtime stage or call any executor.

- [x] **Step 2: Add regression assertions for dry-run artifacts and counts.**

Assert both files exist, carry advisory claim scope, and contain more hypotheses than the bounded execution budget for the fixture project.

- [x] **Step 3: Run the focused closed-loop tests.**

Run: `python -m pytest tools/tests/test_hypothesis_registry.py tools/tests/test_chaosatlas.py -q`

Expected: all tests pass and dry-run remains synthetic/not_run.

### Task 4: Verify and record the stage

**Files:**
- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [x] **Step 1: Run focused regression, compileall, and a fresh offline dry-run.**

Run: `python -m pytest tools/tests/test_hypothesis_registry.py tools/tests/test_chaosatlas.py tools/tests/test_chaosatlas_batch.py -q`

Run: `python -m compileall -q tools/hypothesis_registry.py tools/chaosatlas.py`

- [x] **Step 2: Inspect the generated portrait and registry.**

Confirm that runtime execution eligibility is bounded separately from the total hypothesis count, no final verdict fields exist, and no live mutation or formal knowledge write occurred.

- [x] **Step 3: Record verification output and remaining gap.**

Document that policy selection still consumes the existing runtime candidate pool; a later phase will teach policy to select from registry entries after registry quality is validated.
