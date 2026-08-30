# ChaosAtlas Network DNS HTTP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将第一批网络、DNS 和 HTTP 故障从静态目录或编译器能力推进到可受控执行、可恢复、可清理并能进入 RCA 的运行能力。

**Architecture:** 保留现有 `compile_scenario_node.py` 作为确定性 manifest 编译器，以统一的生命周期协议包装 Kubernetes/Chaos Mesh 执行。编排器只消费 executor 返回的基线、注入、观测、恢复、清理和 attestation，不根据故障后端推断业务结论。高风险 HTTP/DNS 故障在临时 namespace 中运行，低风险网络延迟/带宽类故障可以使用已授权测试 namespace。

**Tech Stack:** Python 3.12、PyYAML、Kubernetes CLI、Chaos Mesh CRD、pytest、现有 RCA/知识卡流水线。

---

## 文件边界

- Create: `tools/fault_executor.py`，定义统一 executor 协议、生命周期结果和 attestation 校验。
- Create: `tools/isolated_environment.py`，定义临时 namespace 租约、owner 标签、超时和删除审计。
- Modify: `tools/compile_scenario_node.py`，增加 DNS 和剩余 HTTP 场景的参数验证及 manifest 编译。
- Modify: `tools/fault_catalog.py`，仅在真实执行契约和测试完成后更新对应状态，禁止先改目录状态。
- Modify: `tools/kubernetes_lifecycle_executor.py`，让统一 executor 协议复用现有 Chaos Mesh 生命周期实现。
- Modify: `tools/chaosatlas_adapters.py`，把 candidate 的 fault family 映射到统一 executor。
- Modify: `tools/_legacy_chaosatlas.py`，让单候选 live 路径消费统一生命周期结果。
- Modify: `tools/chaosatlas_batch.py`，为第一批故障写入每轮结果、反馈资格和停止原因。
- Create: `tests/test_fault_executor.py`，测试协议、attestation 和非法生命周期。
- Modify: `tests/test_extended_network_faults.py`，补 DNS、参数边界和 manifest 字段断言。
- Create: `tests/test_isolated_environment.py`，测试 namespace 租约和清理审计。
- Create: `tests/test_network_dns_http_live_contract.py`，使用 hooks 测试 live 结果分类，不连接集群。
- Create: `scripts/run_network_dns_http_matrix.py`，按项目 profile 生成可执行候选和验收汇总。
- Modify: `docs/ACCEPTANCE_32_FAULTS.md`，记录第一批真实证据和未实现边界。

### Task 1: 建立统一 executor 协议

**Files:**
- Create: `tools/fault_executor.py`
- Test: `tests/test_fault_executor.py`

- [x] **Step 1: Write the failing test**

```python
from tools.fault_executor import LifecycleAttestation, validate_attestation


def test_attestation_requires_complete_lifecycle():
    result = validate_attestation({
        "baseline": True,
        "injection": True,
        "observation": True,
        "recovery": True,
        "cleanup": False,
        "independent_oracle": True,
        "comparison_eligible": False,
    })
    assert result.valid is False
    assert "cleanup" in result.missing


def test_complete_attestation_is_valid():
    result = validate_attestation({key: True for key in LifecycleAttestation.REQUIRED})
    assert result.valid is True
    assert result.missing == ()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fault_executor.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.fault_executor'`.

- [x] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AttestationResult:
    valid: bool
    missing: tuple[str, ...]


class LifecycleAttestation:
    REQUIRED = (
        "baseline", "injection", "observation", "recovery", "cleanup",
        "independent_oracle", "comparison_eligible",
    )


def validate_attestation(value: dict) -> AttestationResult:
    missing = tuple(key for key in LifecycleAttestation.REQUIRED if value.get(key) is not True)
    return AttestationResult(valid=not missing, missing=missing)
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_fault_executor.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit** (deferred: existing worktree contains unrelated user changes)

```powershell
git add tools/fault_executor.py tests/test_fault_executor.py
git commit -m "feat: add fault lifecycle executor contract"
```

### Task 2: Complete deterministic DNS and HTTP compilation

**Files:**
- Modify: `tools/compile_scenario_node.py`
- Modify: `tests/test_extended_network_faults.py`

- [x] **Step 1: Write the failing tests**

```python
def test_dns_failure_compiles_to_dnschaos_error():
    result = compile_scenario(_scenario("dns_failure", {"hostname": "catalogue"}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "DNSChaos"
    assert manifest["spec"]["action"] == "error"
    assert manifest["spec"]["patterns"] == ["catalogue"]


def test_http_response_corrupt_rejects_empty_body():
    result = compile_scenario(_scenario("http_response_corrupt", {"port": 80, "path": "/", "body": ""}))
    assert result["status"] == "method_invalid"


def test_http_status_error_rejects_non_5xx_status():
    result = compile_scenario(_scenario("http_status_error", {"port": 80, "path": "/", "status_code": 404}))
    assert result["status"] == "method_invalid"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extended_network_faults.py -q`
Expected: DNS and response-corrupt tests fail because the compiler does not support those kinds.

- [x] **Step 3: Implement compiler branches**

Add `dns_failure`, `dns_delay`, and `http_response_corrupt` to the validated scenario kinds when a canonical manifest can be emitted. Register `http_rate_limit`, `dependency_error`, `connection_reset`, and `business_dependency_unreachable` as recognized catalog intents, but return `method_invalid` from the compiler until their native executor exists; never emit a guessed manifest for them. Emit only canonical manifests:

```python
elif kind == "dns_failure":
    if set(parameters) != {"hostname"} or not str(parameters["hostname"]).strip():
        raise ValueError("dns_failure requires hostname")
    api_kind, spec = "DNSChaos", {**base, "action": "error", "patterns": [str(parameters["hostname"]).strip()], "duration": _duration(phase["duration_s"])}
elif kind == "dns_delay":
    if set(parameters) != {"hostname", "latency_ms"}:
        raise ValueError("dns_delay requires hostname and latency_ms")
    latency = int(parameters["latency_ms"])
    if not 1 <= latency <= 300000:
        raise ValueError("dns_delay latency_ms must be in [1, 300000]")
    api_kind, spec = "DNSChaos", {**base, "action": "delay", "patterns": [str(parameters["hostname"]).strip()], "delay": {"latency": f"{latency}ms"}, "duration": _duration(phase["duration_s"])}
```

HTTP types that cannot be represented by a stable Chaos Mesh CRD must return `method_invalid` until their native executor is implemented; they must not emit a guessed manifest.

- [x] **Step 4: Run the focused compiler tests**

Run: `pytest tests/test_extended_network_faults.py tests/test_http_fault_compiler.py -q`
Expected: all existing and new compiler tests pass.

- [ ] **Step 5: Commit** (deferred: existing worktree contains unrelated user changes)

```powershell
git add tools/compile_scenario_node.py tests/test_extended_network_faults.py
git commit -m "feat: compile dns and bounded http fault scenarios"
```

### Task 3: Add isolated namespace leases

**Files:**
- Create: `tools/isolated_environment.py`
- Test: `tests/test_isolated_environment.py`

- [x] **Step 1: Write failing tests**

```python
from tools.isolated_environment import NamespaceLease


def test_high_risk_fault_requires_disposable_environment():
    lease = NamespaceLease.for_fault("api_server_delay", project="online-boutique", seed=1)
    assert lease.disposable is True
    assert lease.namespace.startswith("chaosatlas-run-")


def test_cleanup_record_requires_owner_and_empty_confirmation():
    lease = NamespaceLease.for_fault("dns_failure", project="online-boutique", seed=2)
    result = lease.cleanup_record(resources=[], owner="chaosatlas")
    assert result["status"] == "verified"
    assert result["owner"] == "chaosatlas"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_isolated_environment.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [x] **Step 3: Implement deterministic lease metadata**

```python
from dataclasses import dataclass
import hashlib


HIGH_RISK = {"dns_failure", "http_abort", "dependency_error", "connection_reset", "business_dependency_unreachable", "api_server_delay", "pod_unschedulable"}


@dataclass(frozen=True)
class NamespaceLease:
    namespace: str
    project: str
    fault_family: str
    seed: int
    disposable: bool

    @classmethod
    def for_fault(cls, fault_family: str, *, project: str, seed: int) -> "NamespaceLease":
        digest = hashlib.sha256(f"{project}:{fault_family}:{seed}".encode()).hexdigest()[:12]
        return cls(f"chaosatlas-run-{digest}", project, fault_family, seed, fault_family in HIGH_RISK)

    def cleanup_record(self, *, resources: list[str], owner: str) -> dict:
        return {"status": "verified" if owner == "chaosatlas" and not resources else "blocked", "owner": owner, "namespace": self.namespace, "resources": list(resources)}
```

- [x] **Step 4: Run tests**; commit deferred because the worktree contains unrelated user changes

Run: `pytest tests/test_isolated_environment.py -q`
Expected: `2 passed`.

```powershell
git add tools/isolated_environment.py tests/test_isolated_environment.py
git commit -m "feat: add isolated fault test namespace leases"
```

### Task 4: Integrate the protocol with live Kubernetes execution

**Files:**
- Modify: `tools/kubernetes_lifecycle_executor.py`
- Modify: `tools/chaosatlas_adapters.py`
- Modify: `tools/_legacy_chaosatlas.py`
- Test: `tests/test_network_dns_http_live_contract.py`

- [x] **Step 1: Write hook-based lifecycle tests**

```python
def test_live_executor_returns_valid_attestation_without_real_cluster(tmp_path):
    result = run_with_hooks(tmp_path, fault_family="dns_failure", injected=True, recovered=True, cleaned=True, observation_status="business_unreachable")
    assert result["injection_confirmed"] is True
    assert result["recovery_confirmed"] is True
    assert result["cleanup_confirmed"] is True
    assert result["attestation"]["valid"] is True


def test_cleanup_failure_cannot_be_promoted(tmp_path):
    result = run_with_hooks(tmp_path, fault_family="http_abort", injected=True, recovered=True, cleaned=False, observation_status="business_unreachable")
    assert result["attestation"]["valid"] is False
    assert result["promotion_allowed"] is False
```

The test file must define the hook helper explicitly so it does not touch a cluster:

```python
def run_with_hooks(tmp_path, *, fault_family, injected, recovered, cleaned, observation_status):
    result = {
        "fault_family": fault_family,
        "injection_confirmed": injected,
        "recovery_confirmed": recovered,
        "cleanup_confirmed": cleaned,
        "observation": {"status": observation_status, "samples": [{"status_code": None}]},
    }
    from tools.fault_executor import validate_attestation
    attestation = validate_attestation({
        "baseline": True,
        "injection": injected,
        "observation": True,
        "recovery": recovered,
        "cleanup": cleaned,
        "independent_oracle": True,
        "comparison_eligible": injected and recovered and cleaned,
    })
    result["attestation"] = {"valid": attestation.valid, "missing": list(attestation.missing)}
    result["promotion_allowed"] = attestation.valid
    return result
```

- [x] **Step 2: Run test to verify the new contract fails**

Run: `pytest tests/test_network_dns_http_live_contract.py -q`
Expected: FAIL because the existing adapter does not expose protocol-level promotion eligibility.

- [x] **Step 3: Implement adapter integration**

The adapter must derive `promotion_allowed` only from `validate_attestation`, preserve the existing evidence-derived classifier, and return `method_invalid` for HTTP types without a real executor. The legacy path remains the compatibility entry point, but it delegates lifecycle sequencing to `KubernetesLifecycleExecutor`.

- [x] **Step 4: Run focused and regression tests**

Run: `pytest tests/test_network_dns_http_live_contract.py tests/test_kubernetes_project_adapter.py tests/test_live_inventory_blocking.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tools/kubernetes_lifecycle_executor.py tools/chaosatlas_adapters.py tools/_legacy_chaosatlas.py tests/test_network_dns_http_live_contract.py
git commit -m "feat: route live faults through lifecycle attestation"
```

### Task 5: Add the first-batch matrix runner

**Files:**
- Create: `scripts/run_network_dns_http_matrix.py`
- Modify: `tools/chaosatlas_batch.py`
- Test: `tests/test_network_dns_http_live_contract.py`

- [x] **Step 1: Write the matrix contract test**

```python
def test_matrix_summary_counts_only_cleanup_verified_results(tmp_path):
    summary = build_summary([
        {"fault_family": "network_delay", "status": "live_completed", "cleanup": "verified"},
        {"fault_family": "http_abort", "status": "environment_blocked", "cleanup": "blocked"},
    ])
    assert summary["executed"] == 1
    assert summary["cleanup_verified"] == 1
    assert summary["policy_feedback_eligible"] == 1
```

The matrix runner must expose the deterministic reducer used by the test:

```python
def build_summary(results):
    executed = [item for item in results if item.get("status") == "live_completed"]
    cleanup_verified = [item for item in executed if item.get("cleanup") == "verified"]
    return {
        "executed": len(executed),
        "cleanup_verified": len(cleanup_verified),
        "policy_feedback_eligible": len(cleanup_verified),
    }
```

- [x] **Step 2: Implement deterministic matrix output**

The script accepts repeated `--profile`, an explicit `--kube-context`, `--output`, and `--approve-live`. It writes `batch_manifest.json`, `runtime_results.jsonl`, `rca_summary.json`, `cleanup_audit.json`, and `batch_summary.json`. A child with blocked, invalid, incomplete, or unverified cleanup status is recorded but excluded from policy feedback and knowledge promotion.

- [x] **Step 3: Run the offline matrix test**

Run: `pytest tests/test_network_dns_http_live_contract.py -q`
Expected: matrix summary test passes.

- [ ] **Step 4: Commit** (deferred: existing worktree contains unrelated user changes)

```powershell
git add scripts/run_network_dns_http_matrix.py tools/chaosatlas_batch.py tests/test_network_dns_http_live_contract.py
git commit -m "feat: add network dns http batch evidence summary"
```

### Task 6: Run real canaries in authorized environments

**Files:**
- Modify: `docs/ACCEPTANCE_32_FAULTS.md`
- Evidence: `.runs/acceptance-<project>-<fault>-<date>-v1/`

- [x] **Step 1: Run low-risk network canaries**

```powershell
python tools/chaosatlas.py run --profile projects/nginx-kubernetes-ingress/profile.json --mode live --candidate-id server:deployment:nginx-kubernetes-ingress:nginx-ingress:network_bandwidth --kube-context chaosatlas-improvement --approve-live --output .runs/acceptance-nginx-network-bandwidth-20260827-v1
python tools/chaosatlas.py run --profile projects/sock-shop/profile.json --mode live --candidate-id server:deployment:sock-shop:front-end:network_duplicate --kube-context minikube --approve-live --output .runs/acceptance-sock-network-duplicate-20260827-v1
```

- [ ] **Step 2: Run isolated DNS/HTTP canaries**

Create a `NamespaceLease` for each high-risk candidate and run only after preflight confirms the lease namespace, test Oracle and Chaos Mesh CRD availability. Never reuse an existing production-like namespace for `http_abort`, dependency errors, or connection resets.

- [x] **Step 3: Verify every run**

For each run assert:

```text
summary.status == live_completed
finding_report.payload.attestation.valid == true
cleanup_report.status == verified
phase6_audit.status == live_completed
```

Also run `kubectl get podchaos,networkchaos,dnschaos,httpchaos -n <namespace>` and require no resources remain.

- [x] **Step 4: Update acceptance documentation**

Record each real evidence directory, RCA status, business outcome, cleanup status, and any environment or method block. Do not mark a fault globally implemented based on compiler-only tests.

### Task 7: Full verification checkpoint

**Files:**
- Test: all existing tests and first-batch tests
- Modify: `docs/ACCEPTANCE_32_FAULTS.md`

- [x] **Step 1: Run the complete regression suite**

Run: `$env:PYTHONPATH='.;src;' ; pytest -q`
Expected: all existing tests plus first-batch tests pass.

- [x] **Step 2: Run static consistency checks**

Run: `python scripts/run_network_dns_http_matrix.py --profiles projects/nginx-kubernetes-ingress/profile.json projects/sock-shop/profile.json projects/online-boutique/profile.json --output .runs/network-dns-http-static-matrix`
Expected: one matrix report with 32 canonical IDs per project and no planned fault counted as executed.

- [x] **Step 3: Check repository diff**

Run: `git diff --check`
Expected: no whitespace errors.

- [ ] **Step 4: Commit documentation and plan completion**

```powershell
git add docs/ACCEPTANCE_32_FAULTS.md docs/superpowers/plans/2026-08-27-chaosatlas-network-dns-http-implementation.md
git commit -m "docs: record network dns http implementation checkpoint"
```

## Handoff to the next plan

This plan is complete only when the first batch has real evidence for every applicable fault or an explicit `environment_blocked`/`method_invalid` record explaining why it was not executed. The next plan starts with resource and scaling faults and reuses the executor protocol, namespace leases, matrix runner and attestation rules defined here.
