# Remaining Eight Faults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit, guarded executor contracts for the eight remaining fault intents without claiming live support where the current cluster cannot safely validate them.

**Architecture:** Extend the existing scenario compiler and Kubernetes API executor with reversible, namespace-scoped mutations. DNS faults use the existing DNSChaos path with capability detection and return `inapplicable` when the daemon cannot mutate the target. Configuration, release, and scheduling faults use object snapshots and deterministic restore checks. API server delay is a disposable-cluster-only guarded capability and remains non-live on shared clusters.

**Tech Stack:** Python 3.12, pytest, Kubernetes API/kubectl adapters, Chaos Mesh manifests, JSON evidence contracts.

---

### Task 1: DNS capability and guarded execution

**Files:**
- Modify: `tools/compile_scenario_node.py`
- Modify: `tools/kubernetes_lifecycle_executor.py`
- Modify: `tools/fault_capability_registry.py`
- Modify: `tests/test_extended_network_faults.py`
- Create: `tests/test_remaining_faults.py`

- [x] Add tests for DNS manifest validation, read-only capability failure, and `inapplicable` classification.
- [x] Implement capability probing for writable resolver state and explicit DNSChaos result mapping.
- [x] Ensure cleanup and recovery probes run even when DNS injection is not confirmed.
- [x] Run focused DNS tests.

### Task 2: Configuration and release mutations

**Files:**
- Modify: `tools/compile_scenario_node.py`
- Modify: `tools/kubernetes_fault_executor.py`
- Modify: `tools/fault_capability_registry.py`
- Modify: `tests/test_kubernetes_fault_executor.py`
- Create: `tests/test_release_faults.py`

- [x] Add compiler tests for `env_misconfiguration`, `secret_rotation`, `rollout_pause`, and `image_pull_failure`.
- [x] Implement immutable snapshots, allow-listed patch paths, and exact restore verification.
- [x] Keep Secret values redacted in evidence and use generated test placeholders only.
- [x] Return `environment_blocked` for missing disposable/test-image prerequisites.
- [x] Run focused configuration/release tests.

### Task 3: Scheduling and control-plane guards

**Files:**
- Modify: `tools/compile_scenario_node.py`
- Modify: `tools/kubernetes_fault_executor.py`
- Modify: `tools/fault_capability_registry.py`
- Modify: `tools/isolated_environment.py`
- Create: `tests/test_platform_high_risk_faults.py`

- [x] Add compiler tests for `pod_unschedulable` and `api_server_delay`.
- [x] Implement disposable-environment checks, node-pool/cluster ownership checks, and fail-closed results.
- [x] Ensure neither fault can execute against a shared namespace or shared control plane.
- [x] Run focused high-risk tests.

### Task 4: Catalog, matrix, documentation, and regression

**Files:**
- Modify: `tools/fault_catalog.py`
- Modify: project profiles under `projects/`
- Modify: `docs/ACCEPTANCE_32_FAULTS.md`
- Modify: `tests/test_fault_catalog.py`
- Modify: `tests/test_fault_capability_registry.py`

- [x] Mark a fault `implemented` only when its guarded executor and contract tests pass; leave live-inapplicable types explicitly guarded.
- [x] Add per-project `planned` or `inapplicable` reasons for the eight types until canaries exist.
- [x] Run full test suite, compileall, and diff check.
- [x] Record remaining live validation requirements and evidence paths.
