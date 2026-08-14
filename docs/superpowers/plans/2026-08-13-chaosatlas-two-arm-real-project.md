# ChaosAtlas Two-Arm Real-Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline-gated and runtime-ready three-project comparison for `ChaosAtlas-full` versus `ChaosAtlas-ablation`, with independent discovery, two repetitions per executed hypothesis, and auditable evidence.

**Architecture:** A new versioned experiment root contains frozen project manifests, byte-comparable method bundles, and runtime reports. A deterministic protocol module owns the 18-call matrix and 144-unit budget; existing project-specific deployment/oracle helpers are reused only behind fresh project adapters. A fail-closed preflight prevents model calls or Chaos Mesh mutations until all static and cluster gates pass.

**Tech Stack:** Python 3, PyYAML, pytest, Kubernetes server-side dry-run, Chaos Mesh CRDs, SHA-256 manifests.

---

### Task 1: Freeze the approved design artifact

**Files:**
- Add: `docs/superpowers/specs/2026-08-13-chaosatlas-two-arm-real-project-design.md`

- [ ] **Step 1: Verify the approved design content**

Run:

```powershell
git diff --check -- docs/superpowers/specs/2026-08-13-chaosatlas-two-arm-real-project-design.md
```

Expected: exit code `0`.

- [ ] **Step 2: Commit only the design artifact**

```powershell
git add -- docs/superpowers/specs/2026-08-13-chaosatlas-two-arm-real-project-design.md
git commit -m "docs: define two-arm real-project experiment"
```

Do not stage or modify unrelated existing changes.

### Task 2: Add the formal experiment contract

**Files:**
- Create: `tools/chaosatlas_two_arm_protocol.py`
- Test: `tools/tests/test_chaosatlas_two_arm_protocol.py`

- [ ] **Step 1: Write failing tests**

Test the exact matrix `3 projects x 2 methods x 3 seeds`, the 8/4/2 hypothesis budget, rejection of unknown methods/projects, paired common-input hash equality, and classification of `budget_not_executed`.

- [ ] **Step 2: Run the focused tests and verify the expected import/behavior failure**

```powershell
& "$env:CODEX_PYTHON" -m pytest tools/tests/test_chaosatlas_two_arm_protocol.py -q
```

Expected: fail because the protocol module is not implemented.

- [ ] **Step 3: Implement the minimal deterministic contract**

Expose:

```python
PROJECTS = ("online-boutique", "opentelemetry-demo", "sock-shop")
METHODS = ("ChaosAtlas-full", "ChaosAtlas-ablation")
SEEDS = (1001, 1002, 1003)
MAX_HYPOTHESES = 8
MAX_EXECUTED_HYPOTHESES = 4
REPETITIONS = 2
MAX_RUNTIME_UNITS = 144
```

Add functions for matrix enumeration, canonical JSON hashing, paired-input validation, output-order budget selection, and result classification. Do not call models or kubectl from this module.

- [ ] **Step 4: Run focused tests and the existing contamination tests**

Expected: all focused tests pass; existing contamination tests remain green.

### Task 3: Build fresh three-project manifests and method bundles

**Files:**
- Create: `tools/build_two_arm_real_project_inputs.py`
- Test: `tools/tests/test_build_two_arm_real_project_inputs.py`
- Generate only under: `artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-13/`

- [ ] **Step 1: Write failing tests**

Cover namespace allowlists, exact project identity, no old runtime paths/candidate IDs/mutation paths in prompt-facing inputs, full-only reviewed cross-project knowledge, ablation knowledge absence, and byte-identical shared input hashes.

- [ ] **Step 2: Run tests and verify they fail for the missing builder**

- [ ] **Step 3: Implement the builder**

Consume only fresh source/deployment manifests and source-only topology facts. Emit per project and seed:

```text
manifests/<project>/manifest.json
input_bundles/<project>/seed-<seed>/common.json
input_bundles/<project>/seed-<seed>/chaosatlas-full.json
input_bundles/<project>/seed-<seed>/chaosatlas-ablation.json
input_bundles/<project>/seed-<seed>/*.prompt.txt
```

The full bundle may contain only a reviewed generic knowledge projection. The ablation bundle must contain `knowledge_view: null`. Record source hashes, prompt hashes, method IDs, and contamination-audit status.

- [ ] **Step 4: Generate and validate the new input root**

Expected: 18 method bundles, 18 prompts, 9 common inputs, zero contamination findings, and no writes to historical experiment roots.

### Task 4: Add the model-output compiler and runtime budget ledger

**Files:**
- Create: `tools/run_two_arm_real_project_discovery.py`
- Test: `tools/tests/test_run_two_arm_real_project_discovery.py`

- [ ] **Step 1: Write failing tests**

Test JSON schema parsing, maximum 8 hypotheses, deterministic first-four compiled selection, rejection of shell/kubectl/cross-namespace actions, separate `budget_not_executed`, and two repetition records per executed hypothesis.

- [ ] **Step 2: Run the focused tests and verify failure**

- [ ] **Step 3: Implement offline/default dry-run mode**

The runner must refuse formal model calls unless the project preflight manifest is `runtime_ready`. It must record prompt/input hashes and model output metadata without exposing credentials. It must never select a mutation from historical artifacts.

- [ ] **Step 4: Implement runtime handoff records**

Emit canonical intents for the existing project runner adapters, with `replicate=1` and `replicate=2` explicitly represented. No Kubernetes mutation belongs in the discovery module itself.

### Task 5: Add three project runtime profiles and preflight

**Files:**
- Create: `tools/prepare_two_arm_runtime_profiles.py`
- Test: `tools/tests/test_prepare_two_arm_runtime_profiles.py`
- Generate only under: `artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-13/runtime_profiles/`

- [ ] **Step 1: Write failing tests**

Reject mutable images, non-approved namespaces, missing business oracles, loadgenerator contamination for Online Boutique, missing trace-unavailable declaration for OTel, and health-only oracle definitions for Sock Shop.

- [ ] **Step 2: Run tests and verify failure**

- [ ] **Step 3: Implement profiles**

Use the existing fresh manifests as source material but create new revisioned outputs. Preserve exact project commits and image provenance. Each profile must include server-side dry-run requirements, baseline windows, recovery rehearsal, cleanup scan, and oracle contract.

- [ ] **Step 4: Run offline profile gates and sensitive-information scan**

Expected: Online Boutique and Sock Shop may proceed only if their immutable image and oracle gates pass; OTel remains blocked until all image provenance is resolved. No API keys or tokens may be read or emitted.

### Task 6: Execute namespace-first cluster gates, one project at a time

**Files:**
- Modify only the new runtime profile/report paths.

- [ ] **Step 1: Verify current context, nodes, and residual Chaos resources**

Run the user-authorized namespace checks before each project. Do not operate another project namespace concurrently.

- [ ] **Step 2: Apply only the project namespace and run server-side dry-run**

Use the approved namespace for that project, then validate namespaced resources. Stop on any non-local resource or existing residual Chaos object.

- [ ] **Step 3: Deploy and run two failure-free business baseline windows**

Record all oracle requests and responses. Do not start model calls if either baseline window fails.

- [ ] **Step 4: Run recovery/cleanup rehearsal and global residual scan**

Require stable washout before marking the project `runtime_ready`.

### Task 7: Run the 18 calls and up to 144 runtime units

**Files:**
- Write only under: `artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-13/runtime_results/`

- [ ] **Step 1: Run one project/method/seed at a time**

Keep full and ablation outputs separate. The ablation run must not read the full output or current-project feedback.

- [ ] **Step 2: For each selected hypothesis run repetitions 1 and 2**

Every repetition must pass baseline, injection confirmation, observation, recovery, Chaos deletion, global residual scan, and washout. A failed second repetition invalidates the pair; do not add a third repetition.

- [ ] **Step 3: Stop immediately on cleanup, namespace, oracle, compiler, or transport stop rules**

Record `environment_blocked` or `method_invalid` rather than converting infrastructure failures into weakness results.

### Task 8: Validate, report, and submit only formal evidence

**Files:**
- Create: `artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-13/reports/`
- Modify: none of the historical result directories.

- [ ] **Step 1: Run focused and full relevant tests**

- [ ] **Step 2: Verify every report status, hash, cleanup, washout, and method isolation field**

- [ ] **Step 3: Run contamination and sensitive-information audits**

- [ ] **Step 4: Review git diff and stage only the new specification, protocol tools, tests, profiles, and formal evidence**

- [ ] **Step 5: Commit and push only the formal changes after fresh verification**
