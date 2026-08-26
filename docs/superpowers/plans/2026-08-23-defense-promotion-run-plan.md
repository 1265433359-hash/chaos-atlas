# Defense Promotion In `chaosatlas run` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate explicit repeated-defense promotion, conflict downgrade, and optional advisory metadata into the auditable `chaosatlas run` lifecycle.

**Architecture:** Keep `tools/defense_knowledge.py` as the deterministic promotion engine. Add a small orchestration helper that selects only immediate child run directories under an explicitly supplied history root, records rejected inputs, and publishes artifacts only to an explicitly supplied write root. The main run state machine receives a checkpointed `promote_defense` stage; existing retrieval remains read-only and existing live gates remain unchanged.

**Tech Stack:** Python 3, pathlib, JSON artifacts, pytest.

---

### Task 1: Define promotion-stage contracts

**Files:**
- Create: `tools/defense_promotion_stage.py`
- Test: `tools/tests/test_defense_promotion_stage.py`

- [ ] **Step 1: Write failing tests for explicit child selection and rejection reporting**

```python
def test_select_history_children_only_reads_immediate_valid_run_roots(tmp_path):
    valid = tmp_path / "r1"
    valid.mkdir()
    for name in ("run_manifest.json", "classify.json", "observe.json", "cleanup_report.json"):
        (valid / name).write_text("{}\n", encoding="utf-8")
    nested = tmp_path / "nested" / "r2"
    nested.mkdir(parents=True)
    result = select_history_children(tmp_path)
    assert [item.name for item in result["selected"]] == ["r1"]
    assert result["rejected"][0]["reason"] == "missing_required_artifacts"
```

- [ ] **Step 2: Run the focused test and verify the expected missing-symbol failure**

Run: `python -m pytest tools/tests/test_defense_promotion_stage.py -q --basetemp .pytest-tmp-defense-stage`

Expected: FAIL because `tools.defense_promotion_stage` does not exist.

- [ ] **Step 3: Implement deterministic selection and stage payload helpers**

Implement `select_history_children(root)`, `build_not_run_payload(reason, rejected)`, and `build_conflict_payload(...)`. Selection must sort children by name, require the four artifact files, reject symlinked/non-directory children, and never recurse.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m pytest tools/tests/test_defense_promotion_stage.py -q --basetemp .pytest-tmp-defense-stage`

Expected: PASS.

### Task 2: Add conflict-safe promotion wrapper

**Files:**
- Modify: `tools/defense_knowledge.py`
- Modify: `tools/defense_promotion_stage.py`
- Test: `tools/tests/test_defense_knowledge.py`
- Test: `tools/tests/test_defense_promotion_stage.py`

- [ ] **Step 1: Write failing tests for successful promotion and failed promotion without guard**

```python
def test_run_promotion_publishes_local_reusable_card(tmp_path, defense_run_factory):
    history = tmp_path / "history"
    roots = [defense_run_factory(history, "r1"), defense_run_factory(history, "r2")]
    result = promote_from_history(history_root=history, output_root=tmp_path / "out")
    assert result["status"] == "promoted"
    assert result["knowledge_status"] == "local_reusable"
    assert (tmp_path / "out" / "knowledge_promotion.json").is_file()

def test_counterexample_preserves_old_snapshot_and_emits_no_guard(tmp_path, defense_run_factory):
    old = tmp_path / "knowledge" / "old.json"
    old.parent.mkdir()
    old.write_text('{"knowledge_status":"local_reusable","id":"old"}\n', encoding="utf-8")
    result = record_promotion_conflict(old_card=old, run_root=tmp_path / "bad")
    assert result["status"] == "contested"
    assert result["guard_intents"] == []
    assert result["old_snapshot_sha256"]
    assert json.loads(old.read_text(encoding="utf-8"))["id"] == "old"
```

- [ ] **Step 2: Run tests and confirm they fail for the missing wrapper behavior**

Run: `python -m pytest tools/tests/test_defense_knowledge.py tools/tests/test_defense_promotion_stage.py -q --basetemp .pytest-tmp-defense-stage`

Expected: FAIL on the new wrapper APIs.

- [ ] **Step 3: Implement `promote_from_history` and conflict recording**

Call the existing `promote_repeated_defense` only with selected roots. Write `knowledge_promotion.json` and `regression_intents.json` under the stage output. On validation errors, write `knowledge_conflict.json` with old snapshot hash, run fingerprints, failure reason, and `guard_intents=[]`; never overwrite the old card.

- [ ] **Step 4: Run focused promotion tests**

Run: `python -m pytest tools/tests/test_defense_knowledge.py tools/tests/test_defense_promotion_stage.py -q --basetemp .pytest-tmp-defense-stage`

Expected: PASS.

### Task 3: Integrate the stage and CLI flags

**Files:**
- Modify: `tools/chaosatlas.py`
- Modify: `tools/tests/test_run_closed_loop.py`
- Modify: `tools/tests/test_chaosatlas.py`

- [ ] **Step 1: Write failing tests for checkpointed `promote_defense` stage**

Assert that a dry-run without `--defense-history-root` writes a structured `not_run` promotion artifact, that a supplied history root writes a promoted stage, and that `--knowledge-root` is never written.

- [ ] **Step 2: Run the tests and verify the missing-stage failure**

Run: `python -m pytest tools/tests/test_run_closed_loop.py tools/tests/test_chaosatlas.py -q --basetemp .pytest-tmp-closed-loop`

Expected: FAIL on the new stage/CLI arguments.

- [ ] **Step 3: Add orchestration arguments and stage**

Add `defense_history_root` and `knowledge_write_root` parameters to `run_closed_loop`; add matching CLI options. Execute the stage after `learn` and before `regression`, write checkpoint aliases, and keep the stage fail-closed. Publication must require `knowledge_write_root`.

- [ ] **Step 4: Run closed-loop focused tests**

Run: `python -m pytest tools/tests/test_run_closed_loop.py tools/tests/test_chaosatlas.py -q --basetemp .pytest-tmp-closed-loop`

Expected: PASS.

### Task 4: Add advisory provenance without changing authority

**Files:**
- Modify: `tools/chaosatlas.py`
- Modify: `tools/chaosatlas_hypothesis.py`
- Test: `tools/tests/test_chaosatlas.py`

- [ ] **Step 1: Write failing test for advisory metadata and deterministic fallback**

Assert that the hypothesis artifact records `advisory_status=deterministic_fallback` when no advisory provider is configured, and that an injected advisory can only refer to known candidate IDs.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python -m pytest tools/tests/test_chaosatlas.py -q --basetemp .pytest-tmp-advisory`

Expected: FAIL because the hypothesis artifact lacks the metadata contract.

- [ ] **Step 3: Implement allow-listed advisory metadata**

Record provider/model/request hash only when an advisory callback is supplied. Validate output through the existing parser; on timeout, parse failure, or absent provider use deterministic ranking and mark the fallback. Do not change accepted candidate IDs or final classification logic.

- [ ] **Step 4: Run advisory and regression tests**

Run: `python -m pytest tools/tests/test_chaosatlas.py tools/tests/test_chaosatlas_adapters.py -q --basetemp .pytest-tmp-advisory`

Expected: PASS.

### Task 5: Verify Phase 4 exit gate

**Files:**
- Modify: `progress.md`
- Modify: `task_plan.md`

- [ ] **Step 1: Run defense and closed-loop suites**

Run: `python -m pytest tools/tests/test_defense_evidence.py tools/tests/test_defense_knowledge.py tools/tests/test_defense_promotion_stage.py tools/tests/test_knowledge_feedback_loop.py tools/tests/test_run_closed_loop.py tools/tests/test_chaosatlas.py -q --basetemp .pytest-tmp-feedback`

Expected: all focused tests pass.

- [ ] **Step 2: Run syntax and diff checks**

Run: `python -m compileall -q tools` and `git diff --check`

Expected: both commands exit 0.

- [ ] **Step 3: Record exit-gate evidence**

Update `progress.md` with test counts and artifact paths. Mark the Phase 4 integration items complete in `task_plan.md`; leave Train Ticket live execution and Phase 5 deployment patching explicitly pending until their fixtures are implemented.

- [ ] **Step 4: Review the final diff**

Run: `git diff --stat` and `git status --short`; do not stage or revert unrelated user files.

