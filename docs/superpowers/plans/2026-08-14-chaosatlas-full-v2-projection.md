# ChaosAtlas-full-v2 Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** After the frozen Sock Shop full-v1/ablation batch is complete and audited, build a reviewed, hashed `ChaosAtlas-full-v2` projection from generalized test-node, call-chain, applicability, and historical evidence rules, then run a fresh three-project comparison against full-v1 and ablation.

**Architecture:** Keep raw YAML, project knowledge cards, runtime reports, and project-specific graphs outside the LLM-facing projection. A projection builder will extract only cross-project rules with provenance and evidence-state metadata, reject pending or project-specific claims, and emit a versioned immutable JSON plus SHA-256 manifest. A new input-bundle builder will freeze identical common inputs and create three arms: `ChaosAtlas-full-v1`, `ChaosAtlas-full-v2`, and `ChaosAtlas-ablation`; the existing compiler, runner, lifecycle gates, and pending-review policy remain unchanged.

**Tech Stack:** Python 3, JSON, PyYAML, pytest, existing ChaosAtlas input/discovery/runtime tools, SHA-256 manifests.

---

### Task 1: Close and audit the current Sock Shop batch

**Files:**
- Read: `artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-14-sock-shop/runtime_results-r3/batch-progress.json`
- Read: `tools/verify_two_arm_runtime.py`
- Read: `tools/summarize_two_arm_runtime.py`
- Create after completion: a new verified Sock Shop summary/RCA artifact without overwriting r3 evidence

- [ ] Wait for `runtime_results-r3/batch-progress.json` to report `completed_units=48`, then run the existing verifier against all 48 reports.
- [ ] Reject the batch for formal comparison if any report lacks completed status, baseline pass, injection, recovery, cleanup absence confirmation, stable washout, or matching SHA-256 evidence.
- [ ] Confirm `kubectl get podchaos,networkchaos,stresschaos -A` is empty after the batch and that the Sock Shop namespace is restored or intentionally scaled down by the existing runner contract.
- [ ] Summarize full/ablation counts while keeping `human_review=pending` and `knowledge_base_updated=false`.

### Task 2: Inventory eligible knowledge sources

**Files:**
- Read: `raw_yaml/`
- Read: `artifacts/train-ticket/test_node_catalog.json`
- Read: `artifacts/train-ticket/train_ticket_test_slices_graph.json`
- Read: `artifacts/train-ticket/train_ticket_service_graph.json`
- Read: `artifacts/*/knowledge_base/*.json`
- Read: `docs/KNOWLEDGE_BASE.md`
- Read: `docs/PROJECT_SUMMARY.md`

- [ ] Include only evidence with an explicit validation state of `runtime_verified`, `verified`, or equivalent validated runtime evidence.
- [ ] Convert test-node structure into generalized rules such as selector-to-workload mapping, blast-radius shape, critical-path position, and downstream fan-out.
- [ ] Convert call-chain structure into generalized roles such as entrypoint-to-core, core-to-stateful dependency, synchronous downstream, asynchronous queue, and repeated downstream call.
- [ ] Convert fault applicability into bounded rules over fault family, target role, replica evidence, direction, duration, and observed oracle class.
- [ ] Preserve source card/run identifiers and hashes in provenance, but reject raw project names, candidate IDs, old mutation paths, target-specific conclusions, pending RCA, and unreviewed Sock Shop results.

### Task 3: Write failing projection tests

**Files:**
- Create: `tools/tests/test_build_full_v2_projection.py`
- Create: `tools/build_full_v2_projection.py`

- [ ] Add a test that a validated test-node card yields a generalized `test_node_pattern` with no project-specific target identifier.
- [ ] Add a test that a service-slice graph yields a generalized `call_chain_pattern` with role-based positions and no source path leakage.
- [ ] Add a test that a pending or non-runtime card is rejected from the projection.
- [ ] Add a test that a project-specific historical claim is rejected unless it is converted to an abstract rule with provenance.
- [ ] Add a test that the projection contains the required schema, `human_review=pending`, `knowledge_base_updated=false`, source hashes, and a deterministic projection hash.
- [ ] Run `pytest -q tools/tests/test_build_full_v2_projection.py` and observe the expected failure before implementing the builder.

### Task 4: Implement the minimal full-v2 projection builder

**Files:**
- Modify: `tools/build_full_v2_projection.py`
- Test: `tools/tests/test_build_full_v2_projection.py`

- [ ] Implement explicit loaders for knowledge cards, test-node catalogs, service graphs, and slice graphs.
- [ ] Implement a fail-closed normalization layer that emits only:
  - `test_node_patterns`
  - `call_chain_patterns`
  - `fault_applicability_rules`
  - `evidence_boundaries`
  - `provenance`
- [ ] Ensure the projection never emits executable YAML, candidate IDs, mutation paths, raw runtime output, project-specific target names, old RCA text, secrets, or pending classifications.
- [ ] Emit `chaosatlas-generic-knowledge-projection-v2.json`, `projection-manifest.json`, and a SHA-256 for canonical JSON.
- [ ] Run the focused tests and then the existing input contamination tests.

### Task 5: Freeze three-arm input bundles

**Files:**
- Modify: `tools/build_two_arm_real_project_inputs.py`
- Create: `tools/build_three_arm_real_project_inputs.py`
- Create: `tools/tests/test_build_three_arm_real_project_inputs.py`

- [ ] Add a projection loader that requires the v2 schema, deterministic hash, clean sensitive scan, and `human_review=pending`.
- [ ] Preserve the existing v1 projection unchanged for the control arm.
- [ ] Emit three method IDs with byte-identical `common_input`:
  - `ChaosAtlas-full-v1`
  - `ChaosAtlas-full-v2`
  - `ChaosAtlas-ablation`
- [ ] Set only `knowledge_view` and the method ID differently; ablation receives `knowledge_view=null`.
- [ ] Keep the same seeds, model, prompt schema, max 8 generated hypotheses, max 4 executed hypotheses, two repetitions, compiler, namespace scope, lifecycle, and runtime oracle.
- [ ] Refuse non-empty output directories and write a manifest containing input, projection, prompt, and compiled-output hashes.
- [ ] Run the new tests and existing `test_build_two_arm_real_project_inputs.py`.

### Task 6: Run discovery gates before runtime

**Files:**
- Create: a new versioned experiment directory under `artifacts/experiments/chaosatlas_full_v2_comparison_2026-08-14-r1/`
- Read/Run: `tools/run_two_arm_deepseek_discovery.py`
- Read/Run: `tools/open_discovery_mutation_compiler.py`

- [ ] Build fresh bundles for Online Boutique, OpenTelemetry Demo, and Sock Shop only after the current Sock Shop r3 batch is audited.
- [ ] Run preflight and contamination gates for all 3 arms, 3 seeds, and 3 projects.
- [ ] Call DeepSeek only for the new discovery matrix; do not reuse old model outputs as new-arm outputs.
- [ ] Require all selected hypotheses to compile; record invalid cells and do not execute them.
- [ ] Keep API keys outside the repository and redact all saved model output.

### Task 7: Execute the fresh runtime comparison

**Files:**
- Create: `artifacts/experiments/chaosatlas_full_v2_comparison_2026-08-14-r1/runtime_results/`
- Read/Run: existing project-specific runners and batch tools

- [ ] Run each valid selected mutation twice with the existing baseline/inject/observe/recover/cleanup/washout lifecycle.
- [ ] Require per-round recovery, deletion, global residual scan, diagnostics, and SHA-256 verification.
- [ ] Do not merge failed discovery cells, transport failures, or platform failures into method-result statistics.
- [ ] Do not write pending findings into the knowledge base.

### Task 8: Analyze and compare

**Files:**
- Create: `FULL_V2_COMPARISON_REVIEW.md`
- Create: `FULL_V2_COMPARISON_REVIEW.json`
- Create: project-level summaries and verification JSON

- [ ] Report discovery validity, executable mutation yield, weakness yield, no-impact yield, latency degradation, and lifecycle integrity per project and arm.
- [ ] Compare full-v1 versus full-v2 on the same project/seed budget before comparing either against ablation.
- [ ] Treat ablation as a knowledge-removal control, not as a different compiler or topology control.
- [ ] Separate observed business weakness from any specific root cause; do not infer Eureka, cache, retry, registration, or similar mechanisms without direct evidence.
- [ ] Keep `human_review=pending` and `knowledge_base_updated=false`.

### Task 9: Verify, stage, commit, and push

**Files:**
- Only the new v2 projection, tests, necessary builder changes, fresh evidence, and review artifacts

- [ ] Run focused tests, existing verifier tests, contamination/sensitive scans, `git diff --cached --check`, and final evidence verification.
- [ ] Inspect staged paths individually; never use `git add .`.
- [ ] Commit only the v2 comparison and necessary implementation changes, leaving unrelated dirty files untouched.
- [ ] Push `remediation/2026-08-09-review` and report the commit SHA.
