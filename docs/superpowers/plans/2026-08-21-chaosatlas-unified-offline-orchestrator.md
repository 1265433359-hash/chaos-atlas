# ChaosAtlas Unified Offline Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a deterministic `python tools/chaosatlas.py run --mode dry-run` command that starts from a project profile, runs the corrected project-facts -> server-deployment-detection -> experience-retrieval -> hypothesis -> gate -> evidence -> RCA -> knowledge-draft -> regression flow, and writes resumable audit artifacts.

**Architecture:** Add small protocol, adapter, hypothesis, and orchestration modules around existing `project_onboarding`, `build_deployment_capability_pool`, `runtime_applicability_gate`, RCA, knowledge, and regression helpers. The first executor is a deterministic fake executor; CE and native executors remain future adapters behind the same interface. The orchestrator owns stage order, hashes, checkpoints, and fail-closed handling, while existing deterministic classifiers and RCA state machines retain decision authority.

**Tech Stack:** Python 3, dataclasses/typing, JSON artifacts, existing PyYAML helpers, pytest, PowerShell-compatible CLI invocation.

---

## File Map

- Create `tools/chaosatlas_contracts.py`: run context, stage result, artifact and checkpoint contracts.
- Create `tools/chaosatlas_adapters.py`: offline project adapter, server deployment detection adapter, knowledge provider, and fake executor.
- Create `tools/chaosatlas_hypothesis.py`: deterministic hypothesis builder and optional advisory provider boundary.
- Create `tools/chaosatlas.py`: CLI and stage orchestrator; no platform-specific injection code.
- Create `tools/tests/test_chaosatlas_contracts.py`: contract and checkpoint tests.
- Create `tools/tests/test_chaosatlas_adapters.py`: fixture inventory, deployment detection, knowledge retrieval, and fake lifecycle tests.
- Create `tools/tests/test_chaosatlas_hypothesis.py`: ordering, schema, and LLM advisory isolation tests.
- Create `tools/tests/test_chaosatlas.py`: end-to-end dry-run, artifact, resume, and fail-closed tests.
- Create `tools/tests/fixtures/chaosatlas_offline/sock-shop/project_facts.json`: deterministic project facts derived from the existing Sock Shop fixture.
- Create `tools/tests/fixtures/chaosatlas_offline/online-boutique/project_facts.json`: deterministic Online Boutique project facts.
- Create `tools/tests/fixtures/chaosatlas_offline/p02/project_facts.json`: deterministic P02 project facts.
- Modify `docs/PROJECT_ONBOARDING.md`: document the corrected stage order and dry-run command.
- Modify `task_plan.md` and `progress.md`: record the approved offline orchestrator stage and verification evidence.

## Task 1: Add Run and Artifact Contracts

**Files:**
- Create: `tools/chaosatlas_contracts.py`
- Test: `tools/tests/test_chaosatlas_contracts.py`

- [ ] **Step 1: Write failing tests for stable context and stage artifacts.**

Add tests for:

```python
def test_run_context_hash_excludes_output_directory(tmp_path):
    first = RunContext.create(profile_path="profile.json", mode="dry-run", seed=7, output_root=tmp_path / "a")
    second = RunContext.create(profile_path="profile.json", mode="dry-run", seed=7, output_root=tmp_path / "b")
    assert first.input_snapshot_sha256 == second.input_snapshot_sha256

def test_stage_artifact_contains_status_hash_and_claim_scope(tmp_path):
    result = StageResult.completed("inventory", payload={"project_id": "sock-shop"})
    path = write_stage_artifact(tmp_path, result)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["stage"] == "inventory"
    assert saved["status"] == "completed"
    assert saved["output_sha256"]
    assert saved["claim_scope"] == "static"

def test_checkpoint_rejects_unknown_stage(tmp_path):
    with pytest.raises(ValueError, match="unknown stage"):
        write_checkpoint(tmp_path, next_stage="not-a-stage", completed_stages=[])
```

- [ ] **Step 2: Run the focused tests and confirm they fail because the contract module is absent.**

Run:

```powershell
python -m pytest tools/tests/test_chaosatlas_contracts.py -q --basetemp .pytest-tmp-chaosatlas-contracts
```

Expected: collection/import failure for the not-yet-created `tools.chaosatlas_contracts` module.

- [ ] **Step 3: Implement the minimal contracts.**

Define:

```python
STAGES = ("onboard", "inventory", "server_deployment_detection", "mapping", "retrieval", "hypotheses", "gate", "baseline", "execute", "observe", "classify", "rca", "learn", "regression")

@dataclass(frozen=True)
class RunContext:
    run_id: str
    profile_path: str
    mode: str
    seed: int
    input_snapshot_sha256: str
    output_root: str

@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str
    payload: dict[str, Any]
    claim_scope: str = "static"
    errors: tuple[str, ...] = ()
    next_stage: str | None = None

    @classmethod
    def completed(cls, stage: str, payload: dict[str, Any], *, claim_scope: str = "static") -> "StageResult": ...

def write_stage_artifact(output_root: Path, result: StageResult) -> Path: ...
def write_checkpoint(output_root: Path, *, next_stage: str | None, completed_stages: list[str]) -> Path: ...
def load_checkpoint(output_root: Path) -> dict[str, Any]: ...
```

Canonical JSON must use sorted keys and UTF-8. `write_stage_artifact` must write atomically through a temporary file inside the run directory, then replace the destination. Unknown stages and malformed statuses must raise `ValueError`.

- [ ] **Step 4: Run the focused tests and verify they pass.**

Run the same command from Step 2. Expected: all contract tests pass.

- [ ] **Step 5: Commit the contracts.**

```powershell
git add tools/chaosatlas_contracts.py tools/tests/test_chaosatlas_contracts.py
git commit -m "feat: add closed-loop run contracts"
```

## Task 2: Add Offline Project and Executor Adapters

**Files:**
- Create: `tools/chaosatlas_adapters.py`
- Test: `tools/tests/test_chaosatlas_adapters.py`
- Create: `tools/tests/fixtures/chaosatlas_offline/sock-shop/project_facts.json`
- Create: `tools/tests/fixtures/chaosatlas_offline/online-boutique/project_facts.json`
- Create: `tools/tests/fixtures/chaosatlas_offline/p02/project_facts.json`

- [ ] **Step 1: Write failing tests for inventory, server deployment detection, and fake lifecycle.**

Cover these behaviors:

```python
def test_offline_adapter_inventory_is_project_scoped():
    result = OfflineProjectAdapter(facts_path).inventory(profile)
    assert result["project_id"] == "sock-shop"
    assert result["services"]
    assert result["business_oracles"]

def test_server_deployment_detection_builds_candidates_without_runtime_verdict():
    result = adapter.detect(inventory)
    assert result["status"] == "verified"
    assert result["candidates"]
    assert "runtime_verdict" not in result

def test_fake_executor_marks_outputs_as_synthetic_and_completes_cleanup():
    result = FakeExecutor().run(plan)
    assert result["evidence_status"] == "synthetic"
    assert result["lifecycle"] == ["preflight", "baseline", "inject", "observe", "recover", "cleanup"]
    assert result["cleanup_confirmed"] is True
```

- [ ] **Step 2: Run the focused tests and verify they fail for missing adapters.**

```powershell
python -m pytest tools/tests/test_chaosatlas_adapters.py -q --basetemp .pytest-tmp-chaosatlas-adapters
```

Expected: import failure for `tools.chaosatlas_adapters`.

- [ ] **Step 3: Implement adapters by reusing existing deterministic helpers.**

Implement:

```python
class OfflineProjectAdapter:
    def onboard(self, profile_path: Path, workspace_root: Path) -> dict[str, Any]: ...
    def inventory(self, profile: dict[str, Any]) -> dict[str, Any]: ...
    def detect_server_deployment(self, inventory: dict[str, Any]) -> dict[str, Any]: ...
    def map_test_nodes(self, detection: dict[str, Any]) -> dict[str, Any]: ...

class KnowledgeProvider:
    def retrieve(self, *, project_id: str, candidate_space: dict[str, Any], root: Path | None) -> dict[str, Any]: ...

class FakeExecutor:
    def run(self, plan: dict[str, Any]) -> dict[str, Any]: ...
```

`detect_server_deployment` must call the existing manifest-only `build_pool` behavior where the fixture provides manifest roots, preserve manifest hashes, and never consume runtime verdicts. If an input has no valid manifest/source root, return `method_invalid` rather than fabricate a candidate.

The fake executor must return synthetic evidence with `claim_scope="synthetic"`; it may exercise lifecycle and classifier branches but cannot produce a real `weakness`, `defended`, or `confirmed` claim.

- [ ] **Step 4: Run the adapter tests and verify they pass.**

Run the same command from Step 2. Expected: all adapter tests pass.

- [ ] **Step 5: Commit the adapters and fixtures.**

```powershell
git add tools/chaosatlas_adapters.py tools/tests/test_chaosatlas_adapters.py tools/tests/fixtures/chaosatlas_offline
git commit -m "feat: add offline project and executor adapters"
```

## Task 3: Add Experience Retrieval and Advisory Hypothesis Boundary

**Files:**
- Create: `tools/chaosatlas_hypothesis.py`
- Test: `tools/tests/test_chaosatlas_hypothesis.py`

- [ ] **Step 1: Write failing tests for ordering and advisory isolation.**

Test that:

```python
def test_retrieval_happens_after_project_mapping():
    result = build_hypothesis_input(inventory, detection, candidate_space, cards=[])
    assert result["candidate_space"]
    assert result["knowledge_view"] == []

def test_experience_cards_can_change_order_but_not_candidate_truth():
    plain = rank_candidates(candidate_space, cards=[])
    informed = rank_candidates(candidate_space, cards=[local_reusable_card])
    assert plain["candidate_count"] == informed["candidate_count"]
    assert plain["candidate_ids"] != informed["candidate_ids"]

def test_advisory_output_cannot_set_final_status():
    result = parse_advisory_output(raw_hypothesis_json, allowed_candidate_ids={"candidate-1"})
    assert "weakness_status" not in result
    assert "rca_status" not in result
```

- [ ] **Step 2: Run the focused tests and confirm the new module is absent.**

```powershell
python -m pytest tools/tests/test_chaosatlas_hypothesis.py -q --basetemp .pytest-tmp-chaosatlas-hypothesis
```

Expected: import failure for `tools.chaosatlas_hypothesis`.

- [ ] **Step 3: Implement deterministic retrieval and advisory parsing.**

Implement:

```python
def build_hypothesis_input(inventory, detection, candidate_space, cards): ...
def rank_candidates(candidate_space, cards): ...
def parse_advisory_output(raw: str, *, allowed_candidate_ids: set[str]) -> dict[str, Any]: ...
def build_deterministic_hypotheses(candidate_space, ranked_cards) -> dict[str, Any]: ...
```

Use the existing `query_knowledge_base` card summary format where possible. Retrieval is read-only and occurs only after inventory and candidate generation. The deterministic fallback must work with no cards and no LLM backend. If an LLM backend is provided later, its output is constrained to mechanism, expected observations, missing evidence, and next actions; forbidden verdict fields are rejected.

- [ ] **Step 4: Run the focused hypothesis tests and verify they pass.**

Run the same command from Step 2. Expected: all hypothesis tests pass.

- [ ] **Step 5: Commit the hypothesis boundary.**

```powershell
git add tools/chaosatlas_hypothesis.py tools/tests/test_chaosatlas_hypothesis.py
git commit -m "feat: add contextual experience and hypothesis boundary"
```

## Task 4: Implement the Dry-Run Orchestrator and CLI

**Files:**
- Create: `tools/chaosatlas.py`
- Test: `tools/tests/test_chaosatlas.py`

- [ ] **Step 1: Write failing end-to-end tests.**

Add tests for:

```python
def test_dry_run_executes_correct_stage_order_and_writes_all_artifacts(tmp_path): ...
def test_dry_run_never_emits_runtime_weakness_or_defense_claim(tmp_path): ...
def test_invalid_profile_stops_before_inventory(tmp_path): ...
def test_resume_skips_completed_stages_and_reuses_input_hash(tmp_path): ...
def test_non_empty_output_is_rejected_without_overwriting_files(tmp_path): ...
```

The first test must assert the exact stage order from `STAGES`, the presence of every required artifact, and `summary["status"] == "dry_run_ready"`.

- [ ] **Step 2: Run the end-to-end tests and confirm they fail because the CLI is absent.**

```powershell
python -m pytest tools/tests/test_chaosatlas.py -q --basetemp .pytest-tmp-chaosatlas-cli
```

Expected: import/CLI failure for `tools.chaosatlas`.

- [ ] **Step 3: Implement the stage runner and CLI.**

Expose:

```python
def run_closed_loop(*, profile_path: Path, output_root: Path, mode: str = "dry-run", seed: int = 1001, resume: bool = False, knowledge_root: Path | None = None) -> dict[str, Any]: ...
```

The runner must execute this order exactly:

```text
onboard
inventory
server_deployment_detection
mapping
retrieval
hypotheses
gate
baseline
execute
observe
classify
rca
learn
regression
```

Each stage writes its artifact and checkpoint before the next stage begins. `resume=True` loads the checkpoint, verifies the original profile/input hashes, and continues only from the first incomplete stage. A changed input or mismatched artifact hash must stop with `method_invalid`.

The CLI must support exactly:

```text
run --profile PATH --mode dry-run --output PATH [--seed INT] [--resume] [--knowledge-root PATH]
```

Reject `--mode live` in this phase with a clear message that live adapters are not part of the offline milestone. Do not import or call `kubectl`, CE APIs, or external LLM APIs from the dry-run path.

- [ ] **Step 4: Run CLI and end-to-end tests.**

```powershell
python -m pytest tools/tests/test_chaosatlas.py tools/tests/test_chaosatlas_contracts.py tools/tests/test_chaosatlas_adapters.py tools/tests/test_chaosatlas_hypothesis.py -q --basetemp .pytest-tmp-chaosatlas-all
python tools/chaosatlas.py run --help
```

Expected: focused tests pass, and help shows the dry-run command without a live default.

- [ ] **Step 5: Commit the orchestrator.**

```powershell
git add tools/chaosatlas.py tools/tests/test_chaosatlas.py
git commit -m "feat: add offline closed-loop orchestrator"
```

## Task 5: Add Three-Project Offline Replay and Documentation

**Files:**
- Modify: `tools/tests/test_chaosatlas.py`
- Modify: `docs/PROJECT_ONBOARDING.md`
- Modify: `task_plan.md`
- Modify: `progress.md`

- [ ] **Step 1: Write replay tests for Sock Shop, Online Boutique, and P02.**

Parametrize one test over the three fixture profiles and assert that all three use the same stage order, produce the same artifact names, preserve project identity, and produce no live verdicts.

- [ ] **Step 2: Run the replay tests and inspect any project-specific mismatch.**

```powershell
python -m pytest tools/tests/test_chaosatlas.py -k "offline_replay" -q --basetemp .pytest-tmp-chaosatlas-replay
```

Expected: the test fails only for missing fixture data or an explicit contract mismatch, never because a project requires a special orchestrator branch.

- [ ] **Step 3: Implement fixture normalization without adding project-name branches.**

Keep project-specific facts in the three JSON fixtures. The adapter must use profile and fixture data, not `if project_id == ...` branches. Preserve source and manifest hashes in the inventory and server deployment detection artifacts.

- [ ] **Step 4: Update onboarding documentation and persistent plan logs.**

Document the command, stage order, artifact directory, dry-run claim boundary, and the distinction between server deployment detection capability and optional CE/native execution adapters. Record the implementation status and focused test command in `task_plan.md` and `progress.md` without altering unrelated historical entries.

- [ ] **Step 5: Run the complete offline verification set.**

```powershell
python -m pytest tools/tests/test_chaosatlas_contracts.py tools/tests/test_chaosatlas_adapters.py tools/tests/test_chaosatlas_hypothesis.py tools/tests/test_chaosatlas.py -q --basetemp .pytest-tmp-chaosatlas-final
python tools/chaosatlas.py run --profile artifacts/project_profiles/sock-shop/project_profile.json --mode dry-run --output .tmp-chaosatlas-sock-shop
```

Expected: all focused tests pass; the command exits successfully with `dry_run_ready`; no Kubernetes command, CE call, external model call, or runtime weakness/defense claim is produced.

- [ ] **Step 6: Review diff and commit documentation/replay changes.**

```powershell
git diff --check
git status --short
git add tools/tests/test_chaosatlas.py docs/PROJECT_ONBOARDING.md task_plan.md progress.md
git commit -m "test: replay offline orchestrator across three projects"
```

## Verification Checklist

- [ ] Correct order is project facts -> server deployment detection -> mapping -> retrieval -> hypotheses -> gate -> execution/evidence -> RCA -> knowledge -> regression.
- [ ] Server deployment detection is platform-neutral and does not depend on CE API availability.
- [ ] CE/native are future adapters behind the same executor lifecycle, not duplicated orchestration paths.
- [ ] Experience cards influence ranking and hypotheses but cannot create final findings.
- [ ] Fake evidence is marked synthetic and cannot be promoted to runtime knowledge.
- [ ] LLM advisory fields are schema-validated and cannot set verdict/status fields.
- [ ] Every stage has an artifact and checkpoint.
- [ ] Resume verifies input and artifact hashes.
- [ ] Invalid profile, missing Oracle, missing cleanup, and changed input fail closed.
- [ ] Sock Shop, Online Boutique, and P02 run through the same orchestrator code path.
