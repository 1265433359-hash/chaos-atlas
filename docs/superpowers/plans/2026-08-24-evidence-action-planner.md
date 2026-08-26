# Evidence Action Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Add an internal deterministic evidence-action planning stage to `chaosatlas run` so advisory hypotheses become bounded, auditable read-only actions without granting the LLM execution authority.

**Architecture:** Create a pure planner module that validates advisory references against the static candidate registry, derives a fixed read-only action set, and emits stable ordering and hashes. Integrate it after `hypotheses` and before `gate`; dry-run records the artifact, while live execution fails closed when the plan is blocked and otherwise preserves the existing executor/RCA/promotion interfaces.

**Tech Stack:** Python 3, JSON artifacts, existing `chaosatlas.py` stage/checkpoint helpers, pytest.

---

### Task 1: Implement the pure evidence planner

**Files:**
- Create: `tools/evidence_action_planner.py`
- Create: `tools/tests/test_evidence_action_planner.py`

- [ ] **Step 1: Write failing tests for deterministic planning and advisory isolation.**

Add tests that build a two-candidate fixture and assert:

```python
plan = build_evidence_plan(inventory, candidate_space, hypotheses, candidate_budget=1)
assert plan["status"] == "planned"
assert plan["selection"]["candidate_ids"] == ["candidate-1"]
assert all(action["read_only"] for action in plan["actions"])
assert plan["actions"][0]["action_kind"] == "deployment_facts"
```

Also test that an unknown advisory candidate, target mismatch, forbidden action text, and missing recovery contract produce `status="blocked"` without an executable action; repeated identical inputs produce the same `input_sha256` and action order.

- [ ] **Step 2: Run the new tests and verify the expected RED failure.**

Run:

```powershell
python -m pytest tools/tests/test_evidence_action_planner.py -q --basetemp .pytest-tmp-evidence-plan-red
```

Expected: import/function failures because the planner module does not exist yet.

- [ ] **Step 3: Implement the minimum planner contract.**

Implement:

```python
ALLOWED_ACTION_KINDS = {
    "deployment_facts", "service_facts", "pod_state", "pod_events",
    "pod_logs", "business_baseline", "mechanism_evidence",
}

def build_evidence_plan(
    inventory: dict[str, Any],
    candidate_space: dict[str, Any],
    hypotheses: dict[str, Any],
    *,
    candidate_budget: int,
) -> dict[str, Any]: ...
```

The implementation must derive baseline actions from the static candidate registry, map advisory missing-evidence strings only to the allow-listed kinds, reject unknown IDs/signature mismatches/recovery omissions, sort by `(read_only desc, cost asc, candidate_id, action_id)`, cap selected candidates at `candidate_budget`, and include a canonical input hash. It must never copy arbitrary advisory fields into actions.

- [ ] **Step 4: Run the planner tests and refactor only after GREEN.**

Run the same command with `-q`; expected result is all planner tests passing. Keep action generation pure and free of filesystem, subprocess, Kubernetes, or LLM calls.

### Task 2: Integrate the plan into `chaosatlas run`

**Files:**
- Modify: `tools/chaosatlas.py`
- Modify: `tools/tests/test_chaosatlas.py`
- Modify: `tools/kubernetes_project_adapter.py`
- Modify: `tools/tests/test_kubernetes_project_adapter.py`

- [ ] **Step 1: Write failing integration tests.**

Add tests that run dry-run with deterministic and fake advisory providers and assert:

```python
plan = json.loads((output / "evidence_plan.json").read_text(encoding="utf-8"))["payload"]
assert plan["status"] == "planned"
assert (output / "artifact_index.json").exists()
assert any(item["path"] == "evidence_plan.json" for item in index["artifacts"])
```

Add a second test where the fake provider returns an unknown candidate ID and assert the run is `method_invalid`/`environment_blocked` according to the existing mode, no executor is called, and `phase6_audit.json` records the blocked plan.

- [ ] **Step 2: Run the integration tests and verify RED.**

Run:

```powershell
python -m pytest tools/tests/test_chaosatlas.py -q --basetemp .pytest-tmp-evidence-cli-red
```

Expected: missing `evidence_plan.json` or missing planner integration failures.

- [ ] **Step 3: Add the artifact after hypotheses and before gate.**

Import `build_evidence_plan`, build it from the already validated `inventory`, `candidate_space`, and `hypotheses`, and write an envelope to `evidence_plan.json` without adding a new `STAGES` value. Include the artifact in checkpoint reuse and the existing phase6 artifact index. Use the existing one-candidate budget from the execution contract. Add the default recovery contract to runtime candidates from the deployment node's verified availability profile. Do not change candidate truth, scenario compilation, RCA, classification, or knowledge promotion code.

- [ ] **Step 4: Run the integration tests and focused regression.**

Run:

```powershell
python -m pytest tools/tests/test_evidence_action_planner.py tools/tests/test_chaosatlas.py tools/tests/test_chaosatlas_hypothesis.py -q --basetemp .pytest-tmp-evidence-cli-green
```

Expected: all tests pass and dry-run audit remains `knowledge_base_updated=false`.

### Task 3: Enforce live fail-closed behavior and finish verification

**Files:**
- Modify: `tools/chaosatlas.py`
- Modify: `tools/tests/test_chaosatlas.py`
- Modify: `progress.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Write the live gate regression test.**

Use the existing fake live adapter/preflight/executor fixture. Supply a blocked evidence plan input and assert the executor call list remains empty, the result is blocked, and the audit records `evidence_plan.status=blocked`.

- [ ] **Step 2: Implement the smallest live guard.**

Before any live executor call, require the plan payload to be `planned` and its selected candidate IDs to be a subset of the execution contract budget. Otherwise write the normal audit/checkpoint artifacts and return the existing blocked status. Do not add an alternate executor path.

- [ ] **Step 3: Run complete focused verification.**

Run:

```powershell
python -m pytest tools/tests/test_evidence_action_planner.py tools/tests/test_chaosatlas.py tools/tests/test_chaosatlas_hypothesis.py tools/tests/test_deepseek_advisory.py -q --basetemp .pytest-tmp-evidence-final
python -m compileall -q tools
git diff --check
```

Expected: focused tests pass, compilation succeeds, and diff check reports no whitespace errors. No Kubernetes mutation, external model request, or formal knowledge write is part of this verification.

- [ ] **Step 4: Update project records.**

Append a Phase 8 entry to `progress.md` and `task_plan.md` documenting the new artifact, deterministic/live boundaries, focused test count, and remaining limitation: evidence actions are planned and gated, while automatic multi-candidate live iteration remains a later stage.
