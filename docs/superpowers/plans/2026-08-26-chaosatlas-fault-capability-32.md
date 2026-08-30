# ChaosAtlas 32 Fault Capability Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver 32 product-level fault intents with explicit executors, safety contracts, project support matrices, and closed-loop evidence suitable for Nginx, Sock Shop, and Online Boutique.

**Architecture:** `tools/fault_catalog.py` remains the single source of truth. A capability registry maps each implemented `fault_id` to a backend-specific executor that satisfies compile, preflight, inject, confirm, observe, recover, and cleanup contracts. The orchestrator consumes only the normalized result envelope and never calls Chaos Mesh or Kubernetes APIs directly.

**Tech Stack:** Python 3.12, pytest, Kubernetes CLI/API adapters, Chaos Mesh manifests for supported mesh actions, JSON project profiles, existing RCA/knowledge pipeline.

---

### Task 1: Freeze the 32-entry catalog and capability matrix

**Files:**
- Modify: `tools/fault_catalog.py`
- Create: `tools/fault_capability_registry.py`
- Modify: `tools/kubernetes_project_adapter.py`
- Test: `tests/test_fault_catalog.py`
- Test: `tests/test_fault_capability_registry.py`
- Modify: `projects/nginx-kubernetes-ingress/profile.json`
- Modify: `projects/sock-shop/profile.json`
- Modify: `projects/online-boutique/profile.json`

- [ ] **Step 1: Write the failing catalog tests**

```python
def test_catalog_contains_exactly_32_product_fault_ids():
    from tools.fault_catalog import fault_catalog
    catalog = fault_catalog()
    assert len(catalog) == 32
    assert len(set(catalog)) == 32
    assert all(entry["status"] in {"implemented", "planned"} for entry in catalog.values())

def test_unimplemented_faults_fail_closed_in_registry():
    from tools.fault_capability_registry import capability_for
    assert capability_for("config_reload").status == "planned"
    assert capability_for("config_reload").executor is None
```

- [ ] **Step 2: Run the tests and confirm the expected failure**

Run: `pytest -q tests/test_fault_catalog.py tests/test_fault_capability_registry.py`

Expected: FAIL because the catalog currently contains 10 entries and no capability registry exists.

- [ ] **Step 3: Implement the catalog and registry**

Add the 32 IDs from `docs/superpowers/specs/2026-08-26-chaosatlas-fault-capability-32-design-zh-CN.md`. Keep the existing eight entries as `implemented`, keep `config_reload` and `replica_reduction` as `planned`, and mark new entries `planned` until their executor contracts are complete. Add `CapabilitySpec` with `fault_id`, `status`, `backend`, `category`, `risk_level`, and nullable `executor`.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `pytest -q tests/test_fault_catalog.py tests/test_fault_capability_registry.py`

Expected: PASS.

- [ ] **Step 5: Update project support matrices**

Add `fault_support` to the three project profiles. Each entry must contain `status` (`supported`, `inapplicable`, or `planned`) and a non-empty `reason`; do not claim support merely because the catalog contains an ID.

- [ ] **Step 6: Run profile validation**

Run: `pytest -q tests/test_repository_architecture.py tests/test_fault_catalog.py`

Expected: PASS with all profiles validating the 32-ID matrix.

### Task 2: Add normalized executor result contracts

**Files:**
- Modify: `tools/chaosatlas_contracts.py`
- Create: `tools/fault_executor_contracts.py`
- Test: `tests/test_fault_executor_contracts.py`

- [ ] **Step 1: Write the failing result-envelope test**

```python
def test_executor_result_requires_confirmation_recovery_and_cleanup():
    from tools.fault_executor_contracts import validate_executor_result
    errors = validate_executor_result({"fault_id": "pod_kill", "status": "confirmed"})
    assert "injection_confirmation" in errors
    assert "recovery" in errors
    assert "cleanup" in errors
```

- [ ] **Step 2: Run the test to observe the failure**

Run: `pytest -q tests/test_fault_executor_contracts.py`

Expected: FAIL because the validator is missing.

- [ ] **Step 3: Implement the validator**

Require `fault_id`, `target`, `status`, `injection_confirmation`, `observation`, `recovery`, `cleanup`, `evidence_refs`, and `rca`. Reject `status=confirmed` when confirmation, recovery, or cleanup is not verified. Preserve `environment_blocked`, `inapplicable`, and `method_invalid` as non-weakness outcomes.

- [ ] **Step 4: Run focused and existing contract tests**

Run: `pytest -q tests/test_fault_executor_contracts.py tests/test_chaosatlas_contracts.py`

Expected: PASS.

### Task 3: Implement HTTP and business executor family

**Files:**
- Create: `tools/http_fault_executor.py`
- Modify: `tools/chaosatlas_orchestrator.py`
- Modify: `tools/chaosatlas_adapters.py`
- Test: `tests/test_http_fault_executor.py`
- Test: `tests/test_chaosatlas_orchestrator.py`

- [ ] **Step 1: Add failing tests for delay, abort, status, and reset**

Test that each fault compiles to an explicit HTTP action, requires a business probe, returns `inapplicable` when no probe is configured, and never reports a weakness without a baseline and post-injection observation.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `pytest -q tests/test_http_fault_executor.py`

Expected: FAIL because no HTTP executor is registered.

- [ ] **Step 3: Implement the executor and adapter hooks**

Use an injected HTTP client/probe interface. Keep live network mutation behind the existing approval and namespace gates. Emit deterministic dry-run manifests and complete result envelopes for `http_delay`, `http_abort`, `http_status_error`, `http_response_corrupt`, `http_rate_limit`, `dependency_error`, `connection_reset`, and `business_dependency_unreachable`.

- [ ] **Step 4: Run focused and regression tests**

Run: `pytest -q tests/test_http_fault_executor.py tests/test_chaosatlas_orchestrator.py tests/test_offline_acceptance.py`

Expected: PASS.

### Task 4: Implement Kubernetes configuration, release, scaling, and scheduling executors

**Files:**
- Create: `tools/kubernetes_fault_executor.py`
- Modify: `tools/kubernetes_lifecycle_executor.py`
- Modify: `tools/fault_capability_registry.py`
- Test: `tests/test_kubernetes_fault_executor.py`

- [ ] **Step 1: Write failing tests for config reload and replica reduction**

Verify original object state is captured, mutation requires a successful readiness probe, recovery restores the exact original object or replica count, and cleanup is idempotent.

- [ ] **Step 2: Run the tests and confirm failure**

Run: `pytest -q tests/test_kubernetes_fault_executor.py`

Expected: FAIL because the Kubernetes-specific executor is not registered.

- [ ] **Step 3: Implement the executor**

Implement `config_reload`, `config_drift`, `env_misconfiguration`, `secret_rotation`, `rollout_pause`, `image_pull_failure`, `replica_reduction`, `pod_unschedulable`, and `api_server_delay` using dependency-injected Kubernetes operations. Reject destructive actions outside the profile namespace allow-list and restore snapshots in `finally` paths.

- [ ] **Step 4: Run focused tests**

Run: `pytest -q tests/test_kubernetes_fault_executor.py tests/test_fault_executor_contracts.py`

Expected: PASS.

### Task 5: Add resource, network, DNS, storage, and node capability adapters

**Files:**
- Modify: `tools/compile_scenario_node.py`
- Create: `tools/platform_fault_executor.py`
- Modify: `tools/kubernetes_project_adapter.py`
- Test: `tests/test_platform_fault_executor.py`
- Test: `tests/test_compile_scenario_node.py`

- [ ] **Step 1: Add failing compiler tests for the remaining IDs**

Each test asserts the backend, required parameters, target kind, and invalid-parameter failure behavior.

- [ ] **Step 2: Run compiler tests and confirm failure**

Run: `pytest -q tests/test_platform_fault_executor.py tests/test_compile_scenario_node.py`

Expected: FAIL for unregistered fault IDs.

- [ ] **Step 3: Implement backend-specific adapters**

Add guarded support for `disk_pressure`, `file_descriptor_exhaustion`, `process_exhaustion`, `network_bandwidth`, `network_duplicate`, `network_corrupt`, `dns_failure`, and `dns_delay`. Unsupported cluster capabilities return `inapplicable` with evidence instead of falling back to a different fault.

- [ ] **Step 4: Run focused tests and existing suite**

Run: `pytest -q tests/test_platform_fault_executor.py tests/test_compile_scenario_node.py tests/test_fault_catalog.py`

Expected: PASS.

### Task 6: Integrate 32-class discovery, policy, RCA, and knowledge feedback

**Files:**
- Modify: `tools/chaosatlas_hypothesis.py`
- Modify: `tools/policy_controller.py`
- Modify: `tools/rca_runtime_loop.py`
- Modify: `tools/feedback_protocol.py`
- Test: `tests/test_fault_capability_integration.py`

- [ ] **Step 1: Write failing integration tests**

Verify candidate generation sees all applicable implemented IDs, policy selection filters planned/inapplicable IDs, and only complete confirmed results produce knowledge feedback.

- [ ] **Step 2: Run the tests to confirm failure**

Run: `pytest -q tests/test_fault_capability_integration.py`

Expected: FAIL because the policy and feedback layers currently only know the original implemented tuple.

- [ ] **Step 3: Implement catalog-driven integration**

Replace hard-coded family lists with the capability registry and project support matrix. Preserve legacy/shadow/guarded behavior and evaluate stop policy before the next injection. Reject incomplete cleanup or RCA evidence from knowledge promotion.

- [ ] **Step 4: Run the full offline suite**

Run: `pytest -q`

Expected: PASS.

### Task 7: Build project-facing documentation and acceptance artifacts

**Files:**
- Create: `docs/FAULT_CAPABILITY_MATRIX.md`
- Modify: `docs/PROJECT_ONBOARDING.md`
- Create: `scripts/run_fault_matrix.py`
- Test: `tests/test_fault_matrix_report.py`

- [ ] **Step 1: Write failing report-generation test**

Assert that a matrix report lists all 32 IDs, per-project status, evidence links, and aggregate counts for implemented, planned, and inapplicable.

- [ ] **Step 2: Implement the report generator**

Generate deterministic Markdown and JSON artifacts from profiles and run outputs. Include commands for dry-run and approved live execution.

- [ ] **Step 3: Run documentation/report tests**

Run: `pytest -q tests/test_fault_matrix_report.py`

Expected: PASS.

### Task 8: Cross-project canary and final acceptance

**Files:**
- Create: `docs/ACCEPTANCE_32_FAULTS.md`
- Create: `artifacts/acceptance/32-fault-matrix.json`
- Modify: `.planning/2026-08-26-fault-catalog-32/task_plan.md`
- Modify: `.planning/2026-08-26-fault-catalog-32/progress.md`

- [ ] **Step 1: Run dry-run matrix on all projects**

Run: `python tools/chaosatlas.py run --profile projects/nginx-kubernetes-ingress/profile.json --mode dry-run --output .tmp-matrix-nginx` and repeat for Sock Shop and Online Boutique.

- [ ] **Step 2: Run approved live canaries by supported ID**

Use one fault per run, a bounded budget, and explicit `--approve-live`. Capture baseline, injection confirmation, recovery, cleanup, and RCA evidence.

- [ ] **Step 3: Generate and inspect the matrix report**

Run: `python scripts/run_fault_matrix.py --profiles projects/nginx-kubernetes-ingress/profile.json projects/sock-shop/profile.json projects/online-boutique/profile.json --output artifacts/acceptance/32-fault-matrix.json`.

- [ ] **Step 4: Run the complete regression suite**

Run: `pytest -q`.

Expected: all tests pass and no existing implemented fault regresses.

- [ ] **Step 5: Update acceptance documentation and commit the implementation batch**

Record actual supported/planned/inapplicable counts and known limitations in `docs/ACCEPTANCE_32_FAULTS.md`. Commit only the files changed for this plan.

