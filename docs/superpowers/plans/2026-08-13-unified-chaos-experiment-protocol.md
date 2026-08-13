# Unified Chaos Experiment Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make project experiments comparable by enforcing one P02-style lifecycle contract for gates, mutation provenance, injection, recovery, cleanup, washout, and review.

**Architecture:** Add a small side-effect-free shared protocol module that validates lifecycle reports and derives comparison eligibility. Keep project-specific Kubernetes/oracle behavior in adapters. Upgrade P09 to compile discovery hypotheses through the existing deterministic mutation compiler and to emit reports compatible with the shared contract; preserve completed P02/P08 artifacts and verify their existing runners remain compatible.

**Tech Stack:** Python 3, pytest, PyYAML, kubectl/Chaos Mesh through existing runners, JSON evidence artifacts.

---

### Task 1: Add shared lifecycle contract tests

**Files:**
- Create: `tools/tests/test_unified_experiment_protocol.py`

- [ ] **Step 1: Write failing tests for required lifecycle fields**

Add tests that construct a minimal completed report and assert:

```python
from tools.unified_experiment_protocol import (
    REQUIRED_LIFECYCLE_FIELDS,
    comparison_eligibility,
    validate_lifecycle_report,
)

def test_completed_report_requires_all_lifecycle_sections():
    report = {
        "status": "completed",
        "human_review": "pending",
        "baseline": {"pass": True},
        "injection": {"applied": True},
        "recovery": {"recovered": True},
        "cleanup": {"absent_confirmed": True, "residual_resources": []},
        "washout": {"stable": True},
    }
    result = validate_lifecycle_report(report)
    assert result["valid"] is False
    assert "schema_version" in result["errors"]
    assert comparison_eligibility(report)["eligible"] is False
```

- [ ] **Step 2: Run the focused test and confirm the expected import failure**

Run:

```powershell
python -m pytest tools/tests/test_unified_experiment_protocol.py -q
```

Expected: collection fails because `tools.unified_experiment_protocol` does not yet exist.

- [ ] **Step 3: Add tests for successful validation, failed injection, cleanup, and SHA-256 mismatch**

Cover:

```python
def test_completed_report_is_comparison_eligible_when_all_checks_pass():
    report = valid_report()
    assert validate_lifecycle_report(report)["valid"] is True
    assert comparison_eligibility(report) == {
        "eligible": True,
        "reasons": [],
    }

def test_failed_injection_is_not_comparison_eligible():
    report = valid_report()
    report["injection"]["applied"] = False
    assert comparison_eligibility(report)["eligible"] is False
    assert "injection.applied" in comparison_eligibility(report)["reasons"]

def test_residual_chaos_blocks_comparison():
    report = valid_report()
    report["cleanup"]["residual_resources"] = [{"kind": "PodChaos", "name": "leftover"}]
    assert comparison_eligibility(report)["eligible"] is False

def test_mutation_hash_must_match_file_bytes(tmp_path):
    mutation = tmp_path / "mutation.yaml"
    mutation.write_bytes(b"apiVersion: chaos-mesh.org/v1alpha1\n")
    report = valid_report()
    report["mutation"] = {
        "path": str(mutation),
        "sha256": "0" * 64,
    }
    result = validate_lifecycle_report(report)
    assert result["valid"] is False
    assert "mutation.sha256" in result["errors"]
```

- [ ] **Step 4: Run the focused test and confirm the new assertions fail for the missing module**

Run the same pytest command and confirm the failure is still due to the missing implementation, not malformed tests.

### Task 2: Implement the shared lifecycle contract

**Files:**
- Create: `tools/unified_experiment_protocol.py`
- Modify: `tools/tests/test_unified_experiment_protocol.py`

- [ ] **Step 1: Implement constants and pure validators**

Implement:

```python
REQUIRED_LIFECYCLE_FIELDS = (
    "schema_version",
    "project_id",
    "namespace",
    "arm",
    "mutation_id",
    "replicate",
    "mutation",
    "baseline",
    "injection",
    "observation",
    "recovery",
    "cleanup",
    "washout",
    "diagnostics",
    "human_review",
    "status",
)

def validate_lifecycle_report(report: dict[str, Any]) -> dict[str, Any]:
    ...

def comparison_eligibility(report: dict[str, Any]) -> dict[str, Any]:
    ...

def sha256_file(path: Path) -> str:
    ...
```

The validator must:

- require all top-level fields;
- require `human_review == "pending"`;
- require `mutation.path` and a 64-character SHA-256;
- compare the recorded mutation hash to actual file bytes when the path exists;
- require baseline pass, injection applied, recovery recovered, cleanup absent confirmation, washout stable, and an empty residual list for eligibility;
- never call kubectl or external services.

- [ ] **Step 2: Run the focused tests and confirm they pass**

Run:

```powershell
python -m pytest tools/tests/test_unified_experiment_protocol.py -q
```

Expected: all shared-contract tests pass.

- [ ] **Step 3: Run the existing protocol and compiler tests**

Run:

```powershell
python -m pytest tools/tests/test_open_discovery_mutation_compiler.py tools/tests/test_open_discovery_compiler.py tools/tests/test_p02_execution_gate.py -q
```

Expected: all selected existing tests pass.

### Task 3: Add P09 discovery-to-mutation compilation without another model call

**Files:**
- Create: `tools/p09_open_discovery_mutation.py`
- Create: `tools/tests/test_p09_open_discovery_mutation.py`

- [ ] **Step 1: Write failing tests for consuming frozen P09 discovery evidence**

Test that the adapter:

```python
def test_compile_frozen_p09_hypothesis_to_podchaos(tmp_path):
    result = compile_p09_hypothesis(
        hypothesis=sample_hypothesis(),
        topology=sample_topology(),
        runtime_map=sample_runtime_map(),
        output_dir=tmp_path,
    )
    mutation = yaml.safe_load(result["yaml"])
    assert mutation["metadata"]["namespace"] == "chaosatlas-p09"
    assert mutation["kind"] == "PodChaos"
    assert result["provenance"]["human_review"] == "pending"
    assert result["provenance"]["execution_ready"] is False
```

Also test that non-P09 namespaces, missing runtime mappings, unsupported
parameters, and empty output directories fail closed.

- [ ] **Step 2: Run the focused tests and confirm the expected import failure**

Run:

```powershell
python -m pytest tools/tests/test_p09_open_discovery_mutation.py -q
```

- [ ] **Step 3: Implement the adapter using `open_discovery_mutation_compiler`**

The adapter must:

- accept only a compiled P09 hypothesis with namespace `chaosatlas-p09`;
- resolve the target against `topology_profiles/P09/topology.json` and the P09 runtime mapping;
- emit YAML, provenance, and a manifest;
- calculate and record the actual YAML SHA-256;
- never call the model or kubectl;
- write only into a new empty output directory.

- [ ] **Step 4: Run the focused tests and the compiler tests**

Run:

```powershell
python -m pytest tools/tests/test_p09_open_discovery_mutation.py tools/tests/test_open_discovery_mutation_compiler.py -q
```

### Task 4: Upgrade P09 runtime reports to the shared lifecycle contract

**Files:**
- Modify: `tools/run_p09_podchaos.py`
- Modify: `tools/tests/test_p09_pilot.py`

- [ ] **Step 1: Add failing compatibility assertions**

Extend the P09 runner tests to require:

```python
result = json.loads(report_path.read_text(encoding="utf-8"))
assert result["schema_version"] == "unified-lifecycle-v1"
assert result["namespace"] == "chaosatlas-p09"
assert result["baseline"]["pass"] is True
assert result["injection"]["applied"] is True
assert result["recovery"]["recovered"] is True
assert result["cleanup"]["absent_confirmed"] is True
assert result["washout"]["stable"] is True
assert result["human_review"] == "pending"
```

Add a test that ambiguous apply failure still produces all lifecycle sections
and is ineligible for comparison.

- [ ] **Step 2: Run the P09 tests and observe the expected schema assertion failure**

Run:

```powershell
python -m pytest tools/tests/test_p09_pilot.py -q
```

- [ ] **Step 3: Update the P09 runner report shape**

Keep the current P09 namespace and selector protections. Add:

- mutation path and SHA-256;
- normalized `baseline`, `injection`, `observation`, `recovery`,
  `cleanup`, `washout`, and `diagnostics` sections;
- `status` derived from the shared lifecycle contract;
- explicit residual-resource list;
- `human_review: "pending"`.

Preserve the existing cleanup behavior, including cleanup after ambiguous apply
failure. Do not broaden namespace access.

- [ ] **Step 4: Run P09 tests and shared-contract tests**

Run:

```powershell
python -m pytest tools/tests/test_p09_pilot.py tools/tests/test_unified_experiment_protocol.py -q
```

### Task 5: Preserve P02/P08 compatibility and document the standard

**Files:**
- Create: `tools/tests/test_unified_protocol_compatibility.py`
- Modify: `docs/superpowers/specs/2026-08-13-unified-chaos-experiment-protocol-design.md`

- [ ] **Step 1: Add compatibility tests**

Test that:

- P02 formal runner still requires its execution gate before applying a
  mutation;
- P02 mutation reports contain the required evidence needed for normalization;
- P08 static gate remains blocked when its gate report says immutable image,
  deterministic oracle, or resource pilot is incomplete;
- no compatibility test reads a key or calls an external model.

- [ ] **Step 2: Run the compatibility tests**

Run:

```powershell
python -m pytest tools/tests/test_unified_protocol_compatibility.py tools/tests/test_p02_execution_gate.py tools/tests/test_p02_formal_runtime.py tools/tests/test_run_p08_dual_arm.py -q
```

Expected: all selected compatibility tests pass; the historical P02 artifacts
remain untouched.

- [ ] **Step 3: Self-review the design and plan**

Check:

```powershell
rg -n "TODO|TBD|placeholder|later" docs/superpowers/specs/2026-08-13-unified-chaos-experiment-protocol-design.md docs/superpowers/plans/2026-08-13-unified-chaos-experiment-protocol.md
```

Expected: no placeholders or contradictory requirements.

### Task 6: Verify gates and execute only the newly authorized P09 runtime work

**Files:**
- Create: `artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/teacher-minikube-unified-r1/`
- Create: `artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/P09_UNIFIED_PROTOCOL_REVIEW.md`
- Create: `artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/P09_UNIFIED_PROTOCOL_REVIEW.json`

- [ ] **Step 1: Run P09 static baseline and server-side dry-run**

Verify the active context, P09 nodes/pods, P09 deployment gate, and server-side
dry-run. Operate only in `chaosatlas-p09`.

- [ ] **Step 2: Compile selected frozen P09 hypotheses into a new evidence directory**

Use the existing frozen discovery outputs and/or the selected candidate pool.
Do not call DeepSeek again. Do not overwrite `teacher-minikube-pilot-r1`,
`teacher-minikube-pilot-r2`, or any existing directory.

- [ ] **Step 3: Execute one mutation at a time using the unified lifecycle**

For each newly authorized P09 run:

- baseline;
- apply one mutation;
- confirm injection;
- observe;
- delete and confirm absence;
- wait for recovery and washout;
- verify residual resources;
- capture diagnostics where the P09 adapter supports them.

- [ ] **Step 4: Verify evidence and sensitive-data boundaries**

Check every report status, lifecycle boolean, mutation SHA-256, actual file hash,
diagnostic presence, human review state, and no API key/token patterns.

- [ ] **Step 5: Write the pending human-review report**

The report must distinguish static hypothesis, business weakness evidence, and
specific root-cause evidence. It must not update the knowledge base.

- [ ] **Step 6: Run final tests and inspect staged files**

Run the focused test suite, `git diff --check`, a sensitive-data scan, and:

```powershell
git status --short
git diff --cached --name-only
```

Stage only the protocol, necessary code/tests, and new P09 evidence created by
this task. Leave unrelated existing modifications and untracked directories
unstaged.

- [ ] **Step 7: Commit and report the commit**

Commit with a focused message:

```powershell
git commit -m "feat: unify chaos experiment lifecycle"
```

Push only the current branch after verification.
