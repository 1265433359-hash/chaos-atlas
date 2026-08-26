# Online Boutique Runtime Policy Projection Implementation Plan

> **For agentic workers:** Execute the steps task-by-task with TDD and verification checkpoints.

**Goal:** Build a reusable offline projection bridge and generate a non-empty Online Boutique Shadow replay from frozen runtime evidence.

**Architecture:** A small pure projection module validates historical lifecycle reports and emits canonical policy runtime results plus an audit record. The existing replay evaluator consumes those results; no policy scoring or live execution is added to the bridge.

**Tech Stack:** Python 3, `pytest`, JSON, SHA-256, existing `tools.feedback_protocol` and `tools.evaluate_experiment_value_policy`.

---

### Task 1: Projection contract tests

**Files:**
- Create: `tools/tests/test_project_runtime_projection.py`
- Create: `tools/project_runtime_projection.py`

- [x] **Step 1: Write failing tests for the pure projection contract**

```python
def test_projects_two_complete_weakness_replicates():
    result = project_runtime_results(
        candidates=[candidate("c1")],
        reports=[report("c1", 1), report("c1", 2)],
        project_id="online-boutique",
    )
    assert result["runtime_results"] == [{
        "candidate_id": "c1",
        "classification": "confirmed_weakness",
        "evidence_quality": "complete",
        "source_classification": "weakness_observed",
        "source_report_count": 2,
    }]

def test_rejects_unknown_candidate_and_incomplete_lifecycle():
    with pytest.raises(ValueError, match="unknown candidate"):
        project_runtime_results([candidate("c1")], [report("other", 1), report("other", 2)], "online-boutique")
    broken = report("c1", 2)
    broken["cleanup"]["absent_confirmed"] = False
    with pytest.raises(ValueError, match="lifecycle"):
        project_runtime_results([candidate("c1")], [report("c1", 1), broken], "online-boutique")

def test_rejects_mixed_or_non_weakness_pairs():
    with pytest.raises(ValueError, match="weakness_observed"):
        project_runtime_results([candidate("c1")], [report("c1", 1), report("c1", 2, "no_business_impact_observed")], "online-boutique")
```

- [x] **Step 2: Run the focused test and verify the expected RED failure**

Run: `python -m pytest -q --basetemp .pytest-tmp-projection-red tools/tests/test_project_runtime_projection.py`

Expected: FAIL because `tools.project_runtime_projection` does not yet exist.

### Task 2: Implement the minimal deterministic projector

- [x] **Step 1: Implement validation and projection**

```python
def project_runtime_results(candidates, reports, project_id):
    candidate_ids = {str(row["candidate_id"]) for row in candidates}
    grouped = {}
    for report in reports:
        if report.get("project_id") != project_id:
            raise ValueError("project mismatch")
        candidate_id = str(report.get("mutation_id") or "")
        if candidate_id not in candidate_ids:
            raise ValueError(f"unknown candidate: {candidate_id}")
        if report.get("status") != "completed":
            raise ValueError("report status must be completed")
        if not _lifecycle_complete(report):
            raise ValueError(f"lifecycle incomplete: {candidate_id}")
        grouped.setdefault(candidate_id, []).append(report)
    output = []
    for candidate_id, rows in sorted(grouped.items()):
        replicates = {int(row.get("replicate")) for row in rows}
        if len(rows) < 2 or len(replicates) != len(rows):
            raise ValueError(f"candidate requires two distinct replicates: {candidate_id}")
        if any((row.get("observation") or {}).get("classification") != "weakness_observed" for row in rows):
            raise ValueError("only weakness_observed pairs can be projected")
        output.append({
            "candidate_id": candidate_id,
            "classification": "confirmed_weakness",
            "evidence_quality": "complete",
            "source_classification": "weakness_observed",
            "source_report_count": len(rows),
        })
    return {"runtime_results": output, "projected_candidate_count": len(output), "source_report_count": sum(map(len, grouped.values()))}
```

- [x] **Step 2: Run focused tests and verify GREEN**

Run: `python -m pytest -q --basetemp .pytest-tmp-projection-green tools/tests/test_project_runtime_projection.py`

Expected: all projection tests pass.

### Task 3: Generate and replay the Online Boutique artifact

**Files:**
- Create: `artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/candidates.json`
- Create: `artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/runtime-results.json`
- Create: `artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/projection-audit.json`
- Create: `artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/context.json`
- Create: `artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/shadow-replay.json`
- Create: `artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/shadow-replay-repeat.json`

- [x] **Step 1: Freeze the 55-candidate Online Boutique pool**

Use `artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r3/candidate_pools/online-boutique/candidates.json` as the sole candidate source and record its SHA-256. Use the pool SHA as the project snapshot identifier; do not merge it with the older 24-candidate dependency-edge denominator.

- [x] **Step 2: Project only the eight complete historical reports**

Read the two reports for each of the four IDs under `runtime_results-r2/online-boutique`, preserve raw file hashes and source paths, and reject any report not passing the projector. Do not include the incomplete `runtime_results-r1` report.

- [x] **Step 3: Run the existing replay evaluator twice**

Run:

```powershell
python -m tools.evaluate_experiment_value_policy --candidates artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/candidates.json --runtime-results artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/runtime-results.json --context artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/context.json --output artifacts/policy-rollout/online-boutique-same-pool-r3-shadow-20260824/shadow-replay.json --project-id online-boutique --project-commit a4a27eb6d4052567c5d3fcc991b20e170613026f1d04a6b24e00a628f05b6a47 --seed 1001
```

Repeat to `shadow-replay-repeat.json`; assert equal `input_sha256`, decisions, and full-file SHA-256. Assert `recorded_result_count=4` (four stable projected candidates sourced from eight reports), `cluster_access=false`, `model_called=false`, `mutation_executed=false`, and no knowledge write.

### Task 4: Regression and documentation verification

- [x] **Step 1: Run all policy and full tool tests**

Run: `python -m pytest -q --basetemp .pytest-tmp-projection-final tools/tests/test_project_runtime_projection.py tools/tests/test_evaluate_experiment_value_policy.py tools/tests/test_policy_selection_gate.py tools/tests/test_chaosatlas_batch.py tools/tests/test_chaosatlas.py`

Expected: zero failures.

- [x] **Step 2: Run static checks**

Run: `python -m compileall -q tools` and `git diff --check`.

- [x] **Step 3: Record the evidence boundary**

Append the artifact hashes, source report count, projected count, replay result, and offline-only boundary to `task_plan.md`, `progress.md`, and `findings.md`. Do not claim project-wide superiority or formal knowledge promotion.
