# R5 Dedup Audit And Ablation Runtime Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible offline audit that replaces the coarse R5 canonical key with family/instance identities, freezes Full/Ablation overlap sets, and prepares only the missing Ablation runtime.

**Architecture:** Keep discovery artifacts immutable. A pure identity module normalizes discovery hypotheses and referenced mutation YAMLs, selects one representative per method, and emits family-overlap, strict-overlap, full-only, and ablation-only manifests. A separate audit command writes a fresh, hash-pinned R6 directory; runtime execution remains delegated to the existing namespace-safe runner and is blocked until the selection manifest and server-side gate pass.

**Tech Stack:** Python 3.12, PyYAML, pytest, existing Sock Shop runtime planner and Chaos Mesh gate.

---

### Task 1: Identity normalization contract

**Files:**
- Create: `tools/sock_shop_hypothesis_identity.py`
- Test: `tools/tests/test_sock_shop_hypothesis_identity.py`

- [ ] **Step 1: Write failing tests**

Cover: action/kind aliases; service target extraction from selectors; call-chain inclusion in family identity; duration/delay/loss/CPU/memory/path/direction normalization in instance identity; Full representative selection by confidence then evidence completeness then order; Ablation first structurally complete representative; family overlap versus strict overlap.

- [ ] **Step 2: Run only the new test file and verify the expected import failure**

Run `python -m pytest tools/tests/test_sock_shop_hypothesis_identity.py --basetemp .tmp-r5-identity-red`; expected failure is missing `tools.sock_shop_hypothesis_identity`.

- [ ] **Step 3: Implement pure functions**

Implement `normalize_kind`, `normalize_action`, `normalize_target`, `normalize_call_chain_position`, `normalized_parameters`, `fault_family_key`, `mutation_instance_key`, `select_method_representatives`, and `partition_method_sets`. YAML parsing must be safe-load only; metadata name, namespace, and generated hash are excluded from semantic parameters. Keep method selection independent of runtime outcomes.

- [ ] **Step 4: Run the new tests and focused regression**

Run the identity test file, then the existing Sock Shop discovery/runtime tests with a repository-local basetemp.

### Task 2: Artifact adapter and old/new key audit

**Files:**
- Modify: `tools/sock_shop_hypothesis_identity.py`
- Test: `tools/tests/test_sock_shop_hypothesis_identity.py`

- [ ] **Step 1: Add tests for `runtime_plan.json` candidate loading**

Assert that only candidates referenced by a method's runtime plan are loaded, unreferenced mutation files are reported as ignored, and every selected candidate has a SHA-256 matching its YAML file.

- [ ] **Step 2: Implement loaders and audit output**

Add `load_discovery_records`, `load_runtime_candidates`, `audit_old_and_new_keys`, and `build_overlap_audit`. Preserve raw source paths, source SHA-256, method, hypothesis id, category, confidence, evidence completeness, family key, instance key, and ignored-file counts.

- [ ] **Step 3: Run tests and inspect counts before any runtime action**

Run the focused suite. Do not call Kubernetes or any model API in this task.

### Task 3: Fresh R6 selection manifest

**Files:**
- Create: `tools/build_sock_shop_hypothesis_identity_audit.py`
- Test: `tools/tests/test_build_sock_shop_hypothesis_identity_audit.py`

- [ ] **Step 1: Write failing CLI contract tests**

Test non-empty output refusal, deterministic fixed-seed Ablation-only sampling, hash files, `human_review=pending`, `knowledge_base_updated=false`, and no mutation when inputs are unchanged.

- [ ] **Step 2: Implement the offline CLI**

Inputs are the two R5 discovery JSON files, the two R5 runtime plans, and their mutation roots. Output must be a new non-empty-safe directory containing `identity_config.json`, `old_new_key_audit.json`, `overlap_audit.json`, `selection_manifest.json`, `selection_manifest.sha256`, and `README.md`. Full selected samples reuse only completed existing reports later; the manifest must not silently claim them completed.

- [ ] **Step 3: Run the CLI in a new `r6` directory and verify hashes**

Use a new suffix if the intended directory is non-empty. Verify deterministic rerun in a temporary directory, then retain the first immutable output.

### Task 4: Rebuild Ablation discovery under the approved boundary

**Files:**
- Modify only if needed: `tools/run_sock_shop_confidence_discovery.py`
- Test: existing discovery tests plus a new boundary regression if needed

- [ ] **Step 1: Validate prompt/input boundary**

Confirm Ablation input contains deployment facts, oracle, and shared YAML statistics only, with no knowledge snapshot, call-chain projection, historical evidence, confidence trace, or Full result.

- [ ] **Step 2: Run a fresh Ablation discovery into a new R6 directory**

Use the frozen common input and the registered Full discovery wall-clock cap. Record `self_stop`, `time_cap_hit`, wall-clock, model call count, token counts when returned, request/prompt hashes, and `human_review=pending`.

- [ ] **Step 3: Freeze the new discovery input hash**

Do not alter the selection rule after inspecting generated candidates. If discovery is incomplete, stop and report it; do not create a runtime comparison from an incomplete arm.

### Task 5: Gate and execute only missing Ablation runtime

**Files:**
- Modify only if needed: `tools/run_sock_shop_confidence_runtime.py`
- Test: `tools/tests/test_run_sock_shop_confidence_runtime.py`

- [ ] **Step 1: Add a selection-manifest gate**

Require exact mutation SHA-256, namespace `chaosatlas-sock-shop`, empty prior runtime roots, and no completed-report reuse for Ablation. Full reports may be referenced only where the manifest explicitly records a completed report and its SHA-256.

- [ ] **Step 2: Server-side dry-run and static sensitivity checks**

Dry-run every selected mutation before injection. HTTPChaos platform-blocked candidates remain blocked and outside the runtime denominator; no unsupported candidate is silently replaced.

- [ ] **Step 3: Execute only fresh Ablation candidates**

Run serially with two replicates. After every injection verify recovery, resource deletion, namespace residual scan, global residual scan, and stable washout. Stop on any lifecycle failure and preserve the failed evidence.

### Task 6: Review, archive, and verification

**Files:**
- Create: `tools/review_sock_shop_r5_dedup.py`
- Create: `tools/tests/test_review_sock_shop_r5_dedup.py`
- Create: fresh R6 audit/report artifacts only

- [ ] **Step 1: Independently validate report status and hashes**

Check completed status, baseline, injection, recovery, cleanup, washout, mutation SHA-256, diagnostic SHA-256, and logs/events/Zipkin evidence.

- [ ] **Step 2: Produce conservative comparison tables**

Report stable weaknesses, one-off results, no-impact results, invalid/gate-blocked candidates, family/strict overlap, and timing separately. Do not infer internal causes without direct logs or traces.

- [ ] **Step 3: Run focused regression, secret scan, and diff review**

Do not use `git add .`; stage only the new tools/tests/docs and necessary small manifests after review. Keep pending review out of the knowledge base and do not push until the final evidence boundary is reviewed.
