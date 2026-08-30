"""Controlled Kubernetes lifecycle executor for server deployment detection.

The executor is the live adapter boundary.  It owns only lifecycle sequencing;
RCA and knowledge promotion remain deterministic consumers of its attestation.
All live mutation requires an explicit approval flag and an exact namespace
allow-list.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from http.client import HTTPException
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Callable

import yaml

from tools.dns_network_fallback import build_dns_network_fallback
from tools.run_chaos_experiment import (
    check_mutation,
    delete_resource,
    http_request,
    observation_failure_sample,
    resource_name,
    run_kubectl,
    start_port_forward,
    stop_process,
    wait_for_lifecycle,
    wait_for_port,
    wait_for_target_ready,
    wait_for_container_ready,
)
from tools.fault_executor import validate_attestation


HookMap = dict[str, Callable[..., Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "._-" else "-" for char in str(value))
    normalized = normalized.strip("-")
    if not normalized or normalized in {".", ".."}:
        raise ValueError("action_id must produce a safe filename")
    return normalized


class KubernetesLifecycleExecutor:
    """Run one namespace-scoped mutation through a complete lifecycle."""

    def __init__(
        self,
        *,
        root: Path,
        namespace: str,
        allowed_namespaces: set[str],
        allow_live: bool = False,
        oracle: dict[str, Any] | None = None,
        hooks: HookMap | None = None,
        poll_interval: float = 0.5,
        injection_timeout: float = 45.0,
        recovery_timeout: float = 180.0,
        kube_context: str | None = None,
    ) -> None:
        # Resolve once so paths handed to kubectl remain valid if the caller's
        # working directory changes between artifact creation and execution.
        self.root = Path(root).expanduser().resolve()
        self.namespace = str(namespace or "").strip()
        self.allowed_namespaces = {str(item).strip() for item in allowed_namespaces if str(item).strip()}
        self.allow_live = bool(allow_live)
        self.oracle = deepcopy(oracle or {})
        self.hooks = dict(hooks or {})
        self.poll_interval = poll_interval
        self.injection_timeout = injection_timeout
        self.recovery_timeout = recovery_timeout
        self.kube_context = str(kube_context).strip() if kube_context else None

    def _mutation_path(self, action_id: str, manifest: dict[str, Any]) -> Path:
        mutation_dir = self.root / "runtime" / "mutations"
        safe_action_id = _safe_name(action_id)
        path = mutation_dir / f"{safe_action_id}.yaml"
        # Windows legacy path handling rejects otherwise valid paths at 260
        # characters. Keep the artifact directory stable but shorten only the
        # mutation filename, retaining a deterministic action-id digest.
        if len(str(path)) >= 240:
            digest = hashlib.sha256(str(action_id).encode("utf-8")).hexdigest()[:12]
            path = mutation_dir / f"m-{digest}.yaml"
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        return path

    @staticmethod
    def _selector(manifest: dict[str, Any]) -> dict[str, Any]:
        """Return the canonical selector for nested and Chaos Mesh manifests."""
        spec = manifest.get("spec") or {}
        nested = spec.get("selector")
        if isinstance(nested, dict):
            return nested
        return {
            "namespaces": spec.get("namespaces") or [],
            "labelSelectors": spec.get("labelSelectors") or {},
        }

    def _scope_errors(self, manifest: dict[str, Any]) -> list[str]:
        metadata = manifest.get("metadata") or {}
        namespace = str(metadata.get("namespace") or "")
        selector = self._selector(manifest)
        namespaces = selector.get("namespaces") or [namespace]
        errors: list[str] = []
        if self.namespace not in self.allowed_namespaces:
            errors.append("executor namespace is outside the allow-list")
        if namespace != self.namespace:
            errors.append("mutation namespace does not match executor namespace")
        if namespace not in self.allowed_namespaces:
            errors.append("mutation namespace is outside the allow-list")
        if not isinstance(namespaces, list) or not namespaces or any(str(item) != self.namespace for item in namespaces):
            errors.append("selector namespaces must match executor namespace exactly")
        if not str(metadata.get("name") or ""):
            errors.append("mutation metadata.name is required")
        if not isinstance(selector.get("labelSelectors"), dict) or not selector.get("labelSelectors"):
            errors.append("mutation selector labelSelectors must be non-empty")
        return errors

    def _default_probe(self, phase: str, _manifest: dict[str, Any]) -> dict[str, Any]:
        if str(self.oracle.get("kind") or "http").strip().lower() == "grpc":
            return self._grpc_probe(phase)
        service = str(self.oracle.get("service") or "").strip()
        remote_port = self.oracle.get("remote_port")
        path = str(self.oracle.get("entrypoint") or "/")
        if not service or not isinstance(remote_port, int):
            return {"status": "unavailable", "reason": "business oracle requires service and remote_port", "samples": []}
        local_port = int(self.oracle.get("local_port") or 18090)
        count = max(1, int(self.oracle.get("count") or 1))
        request_headers = self.oracle.get("request_headers")
        headers = (
            {str(key): str(value) for key, value in request_headers.items()}
            if isinstance(request_headers, dict)
            else {}
        )
        expected_body = self.oracle.get("expected_body")
        expected_body = str(expected_body) if expected_body is not None else None
        samples: list[dict[str, Any]] = []
        failures: list[str] = []
        sample_index = 0
        retry_window = (
            float(self.oracle.get("observation_window_s") or 0)
            if phase == "observe"
            else float(self.oracle.get("baseline_retry_window_s") or 0)
        )
        observation_window = max(0.0, retry_window)
        retry_interval = max(0.0, float(self.oracle.get("probe_retry_interval_s") or 1))
        deadline = time.monotonic() + observation_window

        while True:
            process = None
            try:
                if self.kube_context:
                    process = start_port_forward(
                        self.namespace, service, local_port, remote_port, kube_context=self.kube_context
                    )
                else:
                    process = start_port_forward(self.namespace, service, local_port, remote_port)
                wait_for_port("127.0.0.1", local_port, process, float(self.oracle.get("port_forward_timeout") or 15))
                attempt_samples: list[dict[str, Any]] = []
                for _ in range(count):
                    request_args = (
                        local_port,
                        path,
                        "GET",
                        float(self.oracle.get("timeout_s") or 5),
                        None,
                        65536,
                    )
                    sample = http_request(*request_args, headers=headers) if headers else http_request(*request_args)
                    sample_index += 1
                    sample["sample"] = sample_index
                    samples.append(sample)
                    attempt_samples.append(sample)
                passed = bool(attempt_samples) and all(
                    sample.get("status_code") == self.oracle.get("expected_status", 200)
                    and (expected_body is None or expected_body in str(sample.get("body") or ""))
                    for sample in attempt_samples
                )
                if passed:
                    status = "degraded" if failures else "pass"
                    return {
                        "status": status,
                        "phase": phase,
                        "samples": samples,
                        "reason": "business path recovered after transient observation failures" if failures else None,
                    }
                failures.append("business oracle returned a non-success status")
            except (HTTPException, OSError, RuntimeError, TimeoutError) as exc:
                sample_index += 1
                samples.append(observation_failure_sample(sample_index, str(exc)))
                failures.append(str(exc))
            finally:
                stop_process(process)

            if time.monotonic() >= deadline:
                return {
                    "status": "business_unreachable",
                    "phase": phase,
                    "samples": samples,
                    "reason": failures[-1] if failures else "business oracle did not produce a successful sample",
                }
            remaining = max(0.0, deadline - time.monotonic())
            if retry_interval:
                time.sleep(min(retry_interval, remaining))

    def _grpc_probe(self, phase: str) -> dict[str, Any]:
        service = str(self.oracle.get("service") or "").strip()
        remote_port = self.oracle.get("remote_port")
        client_value = str(self.oracle.get("client") or "").strip()
        supporting = self.oracle.get("supporting_services") or []
        if not service or not isinstance(remote_port, int) or not client_value or not isinstance(supporting, list) or not supporting:
            return {"status": "unavailable", "oracle_kind": "grpc", "reason": "grpc oracle requires checkout, client and supporting services", "samples": []}
        client_path = Path(client_value).expanduser().resolve()
        if not client_path.is_file():
            return {"status": "unavailable", "oracle_kind": "grpc", "reason": f"grpc client not found: {client_value}", "samples": []}
        count = max(1, int(self.oracle.get("count") or 1))
        timeout_s = max(0.1, float(self.oracle.get("timeout_s") or 5))
        retry_interval = max(0.0, float(self.oracle.get("probe_retry_interval_s") or 1))
        observation_window = max(0.0, float(self.oracle.get("observation_window_s") or 0) if phase == "observe" else 0.0)
        deadline = time.monotonic() + observation_window
        failures: list[str] = []
        samples: list[dict[str, Any]] = []
        sample_index = 0
        pattern = re.compile(r"\bok\s+oid=(\S+)\s+tracking=(\S+)")
        bindings = [(service, int(remote_port), int(self.oracle.get("local_port") or 18090))]
        for index, item in enumerate(supporting, start=1):
            if not isinstance(item, dict):
                return {"status": "unavailable", "oracle_kind": "grpc", "reason": "invalid supporting service", "samples": []}
            supporting_service = str(item.get("service") or "").strip()
            supporting_port = item.get("remote_port")
            if not supporting_service or isinstance(supporting_port, bool) or not isinstance(supporting_port, int):
                return {"status": "unavailable", "oracle_kind": "grpc", "reason": "invalid supporting service contract", "samples": []}
            bindings.append((supporting_service, supporting_port, int(item.get("local_port") or 18090 + index)))

        while True:
            processes = []
            try:
                for binding_service, binding_remote_port, binding_local_port in bindings:
                    process = start_port_forward(
                        self.namespace,
                        binding_service,
                        binding_local_port,
                        binding_remote_port,
                        kube_context=self.kube_context,
                    ) if self.kube_context else start_port_forward(
                        self.namespace, binding_service, binding_local_port, binding_remote_port
                    )
                    processes.append(process)
                    wait_for_port("127.0.0.1", binding_local_port, process, float(self.oracle.get("port_forward_timeout") or 15))
                command = [
                    sys.executable,
                    str(client_path),
                    f"127.0.0.1:{bindings[0][2]}",
                    f"127.0.0.1:{bindings[1][2]}",
                    str(count),
                ]
                completed = subprocess.run(
                    command,
                    cwd=str(client_path.parent),
                    capture_output=True,
                    text=True,
                    timeout=max(timeout_s * count + 5.0, 10.0),
                    check=False,
                )
                matched = []
                for line in (completed.stdout or "").splitlines():
                    match = pattern.search(line)
                    if match:
                        matched.append({"order_id": match.group(1), "shipping_tracking_id": match.group(2)})
                for item in matched:
                    sample_index += 1
                    samples.append({"sample": sample_index, "observation_status": "pass", **item})
                if completed.returncode == 0 and len(matched) == count:
                    return {
                        "status": "degraded" if failures else "pass",
                        "phase": phase,
                        "oracle_kind": "grpc",
                        "successes": len(matched),
                        "samples": samples,
                        "reason": "gRPC business path recovered after transient observation failures" if failures else None,
                    }
                failures.append((completed.stderr or completed.stdout or "gRPC business oracle did not satisfy the success contract").strip()[-500:])
            except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
                sample_index += 1
                samples.append({**observation_failure_sample(sample_index, str(exc)), "oracle_kind": "grpc"})
                failures.append(str(exc))
            finally:
                for process in processes:
                    stop_process(process)
            if phase != "observe" or time.monotonic() >= deadline:
                return {
                    "status": "business_unreachable",
                    "phase": phase,
                    "oracle_kind": "grpc",
                    "successes": sum(1 for item in samples if item.get("observation_status") == "pass"),
                    "samples": samples,
                "reason": failures[-1] if failures else "gRPC business oracle did not produce a successful sample",
            }
            remaining = max(0.0, deadline - time.monotonic())
            if retry_interval:
                time.sleep(min(retry_interval, remaining))

    def _default_dns_capability_probe(self, target_pods: list[dict[str, Any]], _manifest: dict[str, Any]) -> dict[str, Any]:
        """Check that the target container can safely mutate resolver state."""
        if not target_pods:
            return {"status": "inapplicable", "reason": "DNSChaos target pod list is empty", "checked_pods": []}
        checked: list[dict[str, Any]] = []
        for item in target_pods:
            pod = str(item.get("name") or "").strip()
            if not pod:
                continue
            marker = f"/etc/resolv.conf.chaosatlas-{hashlib.sha256(pod.encode('utf-8')).hexdigest()[:8]}"
            code, stdout, stderr = run_kubectl(
                ["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", f"test -w /etc/resolv.conf; touch {marker}; rm -f {marker}"],
                timeout=20,
                kube_context=self.kube_context,
            )
            checked.append({"pod": pod, "return_code": code, "stdout": stdout, "stderr": stderr})
            if code == 0:
                return {"status": "ready", "resolver_writable": True, "checked_pods": checked}
        return {"status": "inapplicable", "resolver_writable": False, "checked_pods": checked, "reason": "target resolver state is not writable"}

    def _default_dns_fallback(self, manifest: dict[str, Any], capability: dict[str, Any]) -> dict[str, Any] | None:
        """Build a NetworkChaos mutation against the cluster DNS Service."""
        code, stdout, stderr = run_kubectl(
            ["get", "service", "kube-dns", "-n", "kube-system", "-o", "json"],
            timeout=20,
            kube_context=self.kube_context,
        )
        if code != 0:
            return None
        try:
            payload = json.loads(stdout)
            cluster_ip = str(((payload.get("spec") or {}).get("clusterIP") or "")).strip()
        except (json.JSONDecodeError, AttributeError):
            return None
        if not cluster_ip or cluster_ip.lower() == "none":
            return None
        spec = manifest.get("spec") if isinstance(manifest, dict) else {}
        family = "dns_failure" if str((spec or {}).get("action") or "") == "error" else "dns_delay"
        latency_text = str(((spec or {}).get("delay") or {}).get("latency") or "300ms")
        try:
            latency_ms = int(re.sub(r"[^0-9]", "", latency_text))
        except ValueError:
            latency_ms = 300
        metadata = manifest.get("metadata") if isinstance(manifest, dict) else {}
        name = f"{str((metadata or {}).get('name') or 'dns-fault')}-network"
        selector = self._selector(manifest).get("labelSelectors") or {}
        fallback = build_dns_network_fallback(
            namespace=self.namespace,
            selector={str(k): str(v) for k, v in selector.items()},
            dns_cluster_ip=cluster_ip,
            fault_family=family,
            duration_s=30,
            name=_safe_name(name),
            dns_targets=[],
            latency_ms=latency_ms if family == "dns_delay" else None,
        )
        fallback["metadata"]["labels"].update({"chaosatlas.dev/fallback": "dns-network"})
        return fallback

    def _hook(self, name: str, default: Callable[..., Any]) -> Callable[..., Any]:
        return self.hooks.get(name, default)

    def _wait_lifecycle(self, kind: str, namespace: str, name: str, predicate: str) -> Any:
        timeout = self.injection_timeout if predicate == "injected" else self.recovery_timeout
        return wait_for_lifecycle(kind, namespace, name, predicate, timeout, self.poll_interval, kube_context=self.kube_context)

    def _wait_target_ready(
        self,
        namespace: str,
        selector: dict[str, Any],
        expected_count: int | None,
        pre_uids: set[str],
    ) -> Any:
        return wait_for_target_ready(
            namespace,
            selector,
            self.recovery_timeout,
            self.poll_interval,
            expected_pod_count=expected_count,
            pre_kill_uids=pre_uids or None,
            kube_context=self.kube_context,
        )

    def _wait_container_ready(
        self,
        namespace: str,
        selector: dict[str, Any],
        expected_count: int | None,
        pre_restart_counts: dict[str, int],
        target_pod_names: set[str],
        container_names: set[str],
    ) -> Any:
        return wait_for_container_ready(
            namespace,
            selector,
            self.recovery_timeout,
            self.poll_interval,
            expected_pod_count=expected_count,
            pre_restart_counts=pre_restart_counts,
            target_pod_names=target_pod_names,
            container_names=container_names,
            kube_context=self.kube_context,
        )

    def _apply(self, manifest: dict[str, Any], path: Path) -> dict[str, Any]:
        return _apply_default(manifest, path, kube_context=self.kube_context)

    def _delete(self, kind: str, namespace: str, name: str) -> dict[str, Any]:
        return delete_resource(kind, namespace, name, kube_context=self.kube_context)

    def _write_result(self, action_id: str, result: dict[str, Any]) -> Path:
        path = self.root / "runtime" / f"{_safe_name(action_id)}.json"
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        return path

    def run(self, manifest: dict[str, Any], *, action_id: str) -> dict[str, Any]:
        manifest = deepcopy(manifest)
        errors = self._scope_errors(manifest)
        if errors:
            return {"status": "environment_blocked", "errors": errors, "lifecycle": []}
        if not self.allow_live:
            return {"status": "environment_blocked", "errors": ["explicit live approval is required"], "lifecycle": []}

        mutation_path = self._mutation_path(action_id, manifest)
        kind = str(manifest.get("kind") or "")
        namespace = self.namespace
        name = str((manifest.get("metadata") or {}).get("name") or "")
        lifecycle = ["preflight"]
        result: dict[str, Any] = {
            "schema_version": "chaosatlas-kubernetes-lifecycle-v1",
            "action_id": action_id,
            "status": "blocked",
            "mutation_ref": str(mutation_path.relative_to(self.root)).replace("\\", "/"),
            "lifecycle": lifecycle,
            "baseline": None,
            "injection": {"applied": False, "confirmed": False},
            "observation": None,
            "recovery": {"confirmed": False},
            "cleanup": {"confirmed": False},
            "errors": [],
        }
        applied = False
        gate = self._hook(
            "gate",
            lambda _manifest, path: check_mutation(
                path, allowed_namespaces=self.allowed_namespaces, kube_context=self.kube_context
            ),
        )(manifest, mutation_path)
        result["preflight"] = gate
        if gate.get("decision") != "ready_for_injection":
            result["status"] = "environment_blocked"
            result["errors"].append("runtime applicability gate blocked mutation")
            self._write_result(action_id, result)
            return result

        target_pods = ((gate.get("checks") or {}).get("target_pods") or [])
        dns_probe = self.hooks.get("dns_capability_probe")
        if kind == "DNSChaos" and (dns_probe is not None or target_pods):
            capability = (dns_probe or self._default_dns_capability_probe)(target_pods, manifest)
            result["capability"] = capability
            if not isinstance(capability, dict) or capability.get("status") != "ready":
                fallback_builder = self.hooks.get("dns_fallback_builder")
                fallback = (fallback_builder or self._default_dns_fallback)(manifest, capability)
                if fallback is None:
                    result["status"] = "inapplicable"
                    reason = capability.get("reason") if isinstance(capability, dict) else None
                    result["errors"].append(str(reason or "DNS resolver capability is unavailable"))
                    result["outcome_status"] = "inapplicable"
                    result["attestation"] = {
                        "schema_version": "chaosatlas-runtime-result-v1",
                        "valid": False,
                        "missing": ["injection", "observation", "recovery", "cleanup", "independent_oracle", "comparison_eligible"],
                        "comparison_eligible": False,
                        "baseline": False,
                        "injection": False,
                        "observation": False,
                        "recovery": False,
                        "cleanup": False,
                        "independent_oracle": False,
                    }
                    result["promotion_allowed"] = False
                    result["injection_confirmed"] = False
                    result["recovery_confirmed"] = False
                    result["cleanup_confirmed"] = False
                    self._write_result(action_id, result)
                    return result
                manifest = fallback
                kind = "NetworkChaos"
                name = str((manifest.get("metadata") or {}).get("name") or "")
                mutation_path = self._mutation_path(f"{action_id}-dns-network", manifest)
                result["mutation_ref"] = str(mutation_path.relative_to(self.root)).replace("\\", "/")
                result["fallback"] = {"backend": "NetworkChaos", "reason": capability.get("reason"), "manifest": str(mutation_path.relative_to(self.root)).replace("\\", "/")}
                gate = self._hook(
                    "gate",
                    lambda _manifest, path: check_mutation(path, allowed_namespaces=self.allowed_namespaces, kube_context=self.kube_context),
                )(manifest, mutation_path)
                result["preflight"] = gate
                if gate.get("decision") != "ready_for_injection":
                    result["status"] = "environment_blocked"
                    result["errors"].append("DNS NetworkChaos fallback applicability gate blocked mutation")
                    self._write_result(action_id, result)
                    return result

        baseline = self._hook("probe", self._default_probe)("baseline", manifest)
        result["baseline"] = baseline
        lifecycle.append("baseline")
        if baseline.get("status") != "pass":
            result["status"] = "business_not_reachable"
            result["errors"].append("independent business baseline did not pass")
            self._write_result(action_id, result)
            return result

        try:
            apply_result = self._hook("apply", lambda value: self._apply(value, mutation_path))(manifest)
            result["injection"]["apply"] = apply_result
            if int(apply_result.get("return_code", 1)) != 0:
                result["status"] = "apply_failed"
                result["errors"].append(str(apply_result.get("stderr") or "kubectl apply failed"))
            else:
                applied = True
                result["injection"]["applied"] = True
                lifecycle.append("inject")
                injected, injected_state, inject_errors = self._hook(
                    "wait_lifecycle", self._wait_lifecycle
                )(kind, namespace, name, "injected")
                result["injection"].update({"confirmed": bool(injected), "state": injected_state})
                result["errors"].extend(inject_errors)
                if not injected:
                    result["status"] = "injection_not_confirmed"
                else:
                    observation = self._hook("probe", self._default_probe)("observe", manifest)
                    result["observation"] = observation
                    lifecycle.append("observe")

                    selector = self._selector(manifest)
                    target_pods = ((gate.get("checks") or {}).get("target_pods") or [])
                    pre_uids = {str(item.get("uid")) for item in target_pods if item.get("uid")}
                    if kind == "PodChaos" and str((manifest.get("spec") or {}).get("action")) == "container-kill":
                        target_pod_names = {
                            str(record.get("id")).split("/", 2)[1]
                            for record in (injected_state.get("records") or [])
                            if isinstance(record, dict) and len(str(record.get("id") or "").split("/", 2)) >= 2
                        }
                        pre_restart_counts = {
                            str(item.get("name")): int(item.get("restarts", 0) or 0)
                            for item in target_pods
                            if item.get("name")
                        }
                        recovered, recovery_state, recovery_errors = self._hook(
                            "wait_container_ready", self._wait_container_ready
                        )(
                            namespace,
                            selector,
                            len(target_pods) or None,
                            pre_restart_counts,
                            target_pod_names,
                            {str(item) for item in ((manifest.get("spec") or {}).get("containerNames") or [])},
                        )
                    elif kind == "PodChaos":
                        recovered, recovery_state, recovery_errors = self._hook(
                            "wait_target_ready", self._wait_target_ready
                        )(namespace, selector, len(target_pods) or None, pre_uids)
                    else:
                        recovered, recovery_state, recovery_errors = self._hook(
                            "wait_lifecycle", self._wait_lifecycle
                        )(kind, namespace, name, "recovered")
                    result["recovery"] = {"confirmed": bool(recovered), "state": recovery_state}
                    result["errors"].extend(recovery_errors)
                    lifecycle.append("recover")
                    result["status"] = "executed" if recovered else "recovery_timeout"
        finally:
            if applied:
                cleanup = self._hook("delete", self._delete)(kind, namespace, name)
                result["cleanup"] = {"confirmed": bool(cleanup.get("absent_confirmed")), **cleanup}
                lifecycle.append("cleanup")
                if not result["cleanup"]["confirmed"]:
                    result["status"] = "cleanup_failed"

        baseline_ok = result["baseline"].get("status") == "pass"
        observation = result.get("observation") or {}
        observation_ok = isinstance(observation, dict) and observation.get("status") in {
            "pass",
            "business_unreachable",
            "degraded",
        }
        injection_ok = bool(result["injection"].get("confirmed"))
        recovery_ok = bool(result["recovery"].get("confirmed"))
        cleanup_ok = bool(result["cleanup"].get("confirmed"))
        comparison_eligible = all((baseline_ok, injection_ok, bool(observation.get("samples")), recovery_ok, cleanup_ok)) and observation.get("status") in {"pass", "degraded", "business_unreachable"}
        result["outcome_status"] = "observed" if observation.get("status") == "pass" else str(observation.get("status") or result["status"])
        attestation = validate_attestation({
            "baseline": baseline_ok,
            "injection": injection_ok,
            "observation": observation_ok,
            "recovery": recovery_ok,
            "cleanup": cleanup_ok,
            "independent_oracle": baseline_ok and observation_ok,
            "comparison_eligible": comparison_eligible,
        })
        result["attestation"] = {
            "schema_version": "chaosatlas-runtime-result-v1",
            "valid": attestation.valid,
            "missing": list(attestation.missing),
            "comparison_eligible": comparison_eligible,
            "baseline": baseline_ok,
            "injection": injection_ok,
            "observation": observation_ok,
            "recovery": recovery_ok,
            "cleanup": cleanup_ok,
            "independent_oracle": baseline_ok and observation_ok,
        }
        result["promotion_allowed"] = attestation.valid
        result["injection_confirmed"] = injection_ok
        result["recovery_confirmed"] = recovery_ok
        result["cleanup_confirmed"] = cleanup_ok
        self._write_result(action_id, result)
        return result

    def __call__(self, manifest: dict[str, Any], phase: dict[str, Any] | None = None, fault: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = manifest.get("metadata") or {}
        action_id = str(metadata.get("name") or (fault or {}).get("target_node_id") or "runtime-action")
        result = self.run(manifest, action_id=action_id)
        return {
            **result,
            "injection_confirmed": bool((result.get("injection") or {}).get("confirmed")),
            "injected_count": 1 if (result.get("injection") or {}).get("confirmed") else 0,
            "cleanup_confirmed": bool((result.get("cleanup") or {}).get("confirmed")),
            "verdict": "observation_pending" if result.get("status") == "executed" else result.get("status"),
        }


def _apply_default(manifest: dict[str, Any], path: Path, kube_context: str | None = None) -> dict[str, Any]:
    serialized = yaml.safe_dump(manifest, sort_keys=False)
    code, stdout, stderr = run_kubectl(["apply", "-f", str(path)], timeout=30, kube_context=kube_context)
    return {"return_code": code, "stdout": stdout, "stderr": stderr, "manifest": serialized}
