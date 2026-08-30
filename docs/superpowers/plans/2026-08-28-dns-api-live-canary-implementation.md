# DNS and API Server Live Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `dns_failure`, `dns_delay`, and `api_server_delay` executable in safe isolated live canaries.

**Architecture:** DNS keeps DNSChaos as the first backend and adds a namespace-scoped NetworkChaos fallback targeting CoreDNS UDP/TCP 53. API Server Delay uses a disposable Minikube control-plane mutator with explicit snapshot, `tc netem` apply, restore, health check, and teardown. Both return the existing lifecycle/attestation schema and fail closed when prerequisites are absent.

**Tech Stack:** Python 3.12, pytest, Kubernetes/Chaos Mesh CRDs, Minikube Docker driver, `kubectl`, Docker `tc`/`ip` tooling.

---

### Task 1: DNS fallback manifest and capability selection

**Files:**
- Modify: `tools/compile_scenario_node.py`
- Modify: `tools/kubernetes_lifecycle_executor.py`
- Modify: `tools/fault_capability_registry.py`
- Test: `tests/test_remaining_faults.py`

- [x] Add tests asserting DNS fallback manifests target the CoreDNS service on ports 53 and preserve namespace/selector scope.
- [x] Add a DNS backend selector that tries DNSChaos when resolver mutation is ready and emits NetworkChaos fallback when it is not.
- [x] Add strict validation for DNS service name, endpoint presence, UDP/TCP 53 ports, and bounded delay duration.
- [x] Keep fallback results `inapplicable` when CoreDNS discovery or target DNS-dependent oracle is unavailable.
- [x] Run focused DNS tests.

### Task 2: DNS-dependent canary oracle

**Files:**
- Modify: `workloads/resource-canary/app.py`
- Modify: `workloads/resource-canary/Dockerfile`
- Modify: `.runs/remaining-eight-live/profile.json`
- Test: `tests/test_remaining_faults.py`

- [x] Add a `/dns-check` endpoint that resolves the configured service hostname before returning the success body.
- [x] Add profile oracle metadata selecting `/dns-check` for DNS canaries.
- [x] Add tests for the DNS fallback lifecycle and resolver capability gate.
- [x] Rebuild/load the image in the isolated Minikube profile and verify the resource-canary workload is Ready (DNS fallback evidence captured; final attestation rerun pending).

### Task 3: Disposable API Server mutator

**Files:**
- Create: `tools/minikube_control_plane_mutator.py`
- Modify: `tools/kubernetes_fault_executor.py`
- Modify: `tools/isolated_environment.py`
- Test: `tests/test_platform_fault_executor.py`

- [x] Implement `MinikubeControlPlaneMutator` with profile/context validation, control-plane container discovery, qdisc snapshot, bounded `tc netem delay`, and restore verification.
- [x] Wire the mutator into `ControlPlaneDelayExecutor` only when `disposable_cluster=true`.
- [x] Return `environment_blocked` before mutation if Docker access, `tc`, container identity, or disposable ownership checks fail.
- [x] Add unit tests for fail-closed behavior.
- [x] Run focused platform tests.

### Task 4: Live canary and acceptance evidence

**Files:**
- Create: `scripts/run_remaining_three_live.py`
- Modify: `docs/ACCEPTANCE_32_FAULTS.md`
- Test: `tests/test_remaining_faults.py`

- [x] Add an explicit script requiring `--approve-live`, isolated namespace/profile, and evidence output under `.runs/`.
- [x] Run DNS failure and DNS delay against resource-canary and record complete lifecycle evidence (`.runs/remaining-eight-live-r8`; both `live_completed`, attestation valid, cleanup verified).
- [x] Add `scripts/run_api_server_delay_disposable.py` to create a disposable Minikube control-plane profile and run API Server Delay with teardown.
- [ ] Execute the disposable profile, verify no Chaos Mesh resources remain, workload health is restored, and all reports contain attestation/cleanup fields (blocked by Docker/Minikube ACL).
- [x] Run full `pytest -q` and `python -m compileall -q tools src` (`134 passed`; compileall clean).
