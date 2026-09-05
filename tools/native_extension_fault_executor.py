"""Guarded native executor for workload-local runtime extension faults."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Callable

from tools.fault_executor import observation_verdict, validate_attestation


Runner = Callable[..., tuple[int, str, str]]
_FAMILIES = {"extension.queue_backlog", "extension.connection_pool_exhaustion", "extension.runtime_pause"}
_CONTROL_PATH = "/tmp/chaosatlas-extension-control.json"


def _duration(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3600:
        raise ValueError("duration_s must be an integer in [1, 3600]")
    return value


def build_native_extension_mutation(fault_family: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    family = str(fault_family or "").strip()
    params = parameters if isinstance(parameters, dict) else {}
    if family not in _FAMILIES:
        raise ValueError(f"unsupported native extension fault family: {family}")
    if family == "extension.queue_backlog":
        if set(params) != {"queue_name", "depth", "duration_s"}:
            raise ValueError("queue_backlog requires queue_name, depth and duration_s")
        name, depth = str(params["queue_name"]).strip(), params["depth"]
        duration = _duration(params["duration_s"])
        if not name or len(name) > 128 or not name.replace("-", "").replace("_", "").replace(".", "").isalnum():
            raise ValueError("queue_name contains unsafe characters")
        if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 1_000_000:
            raise ValueError("queue depth must be in [1, 1000000]")
        control = {"mode": "queue_backlog", "queue_name": name, "depth": depth, "duration_s": duration}
    elif family == "extension.connection_pool_exhaustion":
        if set(params) != {"pool_name", "connections", "duration_s"}:
            raise ValueError("connection_pool_exhaustion requires pool_name, connections and duration_s")
        name, connections = str(params["pool_name"]).strip(), params["connections"]
        duration = _duration(params["duration_s"])
        if not name or len(name) > 128 or not name.replace("-", "").replace("_", "").replace(".", "").isalnum():
            raise ValueError("pool_name contains unsafe characters")
        if isinstance(connections, bool) or not isinstance(connections, int) or not 1 <= connections <= 10_000:
            raise ValueError("connections must be in [1, 10000]")
        control = {"mode": "connection_pool_exhaustion", "pool_name": name, "connections": connections, "duration_s": duration}
    else:
        if set(params) != {"target_process", "pause_ms", "duration_s"}:
            raise ValueError("runtime_pause requires target_process, pause_ms and duration_s")
        process = str(params["target_process"]).strip()
        duration = _duration(params["duration_s"])
        if not process or len(process) > 128 or not process.replace("-", "").replace("_", "").replace(".", "").replace(":", "").isalnum():
            raise ValueError("target_process contains unsafe characters")
        pause = params["pause_ms"]
        if isinstance(pause, bool) or not isinstance(pause, int) or not 1 <= pause <= 300_000:
            raise ValueError("pause_ms must be in [1, 300000]")
        control = {"mode": "runtime_pause", "target_process": process, "pause_ms": pause, "duration_s": duration}
    encoded = base64.b64encode(json.dumps(control, sort_keys=True, separators=(",", ":")).encode()).decode("ascii")
    return {
        "fault_family": family,
        "parameters": dict(params),
        "control": control,
        "control_path": _CONTROL_PATH,
        "command": ["sh", "-ceu", f"printf '%s' '{encoded}' | base64 -d > {_CONTROL_PATH}"],
        "cleanup_command": ["sh", "-ceu", f"rm -f -- {_CONTROL_PATH}"],
    }


class NativeExtensionFaultExecutor:
    """Execute a workload-local extension agent with full lifecycle evidence."""

    def __init__(self, *, namespace: str, allowed_namespaces: set[str], allow_live: bool = False, isolated: bool = False, runner: Runner | None = None, probe: Callable[[str], dict[str, Any]] | None = None, capability_probe: Callable[[str, str], dict[str, Any]] | None = None, target_selector: dict[str, str] | None = None) -> None:
        self.namespace = str(namespace or "").strip()
        self.allowed_namespaces = {str(item).strip() for item in allowed_namespaces if str(item).strip()}
        self.allow_live = bool(allow_live)
        self.isolated = bool(isolated)
        self.runner = runner
        self.probe = probe
        self.capability_probe = capability_probe or self._default_capability_probe
        self.target_selector = {str(key): str(value) for key, value in (target_selector or {}).items() if str(key).strip() and str(value).strip()}

    def _run(self, args: list[str], timeout: int = 45) -> tuple[int, str, str]:
        if self.runner is None:
            raise RuntimeError("native extension runner is not configured")
        try:
            return self.runner(args, timeout=timeout)
        except TypeError:
            return self.runner(args)

    def _target_pod(self, selector: dict[str, str]) -> tuple[str | None, str | None]:
        label = ",".join(f"{key}={value}" for key, value in sorted(selector.items()))
        code, stdout, stderr = self._run(["get", "pods", "-n", self.namespace, "-l", label, "-o", "json"])
        if code != 0:
            return None, (stderr or stdout).strip() or "pod discovery failed"
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return None, f"invalid pod JSON: {exc}"
        for item in (payload.get("items") if isinstance(payload, dict) else []) or []:
            metadata = item.get("metadata") if isinstance(item, dict) else {}
            status = item.get("status") if isinstance(item, dict) else {}
            if (status or {}).get("phase") == "Running" and (metadata or {}).get("name"):
                return str(metadata["name"]), None
        return None, "no Running target pod matched selector"

    def _default_capability_probe(self, pod: str, family: str) -> dict[str, Any]:
        capability = {"extension.queue_backlog": "queue", "extension.connection_pool_exhaustion": "pool", "extension.runtime_pause": "pause"}[family]
        script = f"set -eu; command -v sh >/dev/null 2>&1; command -v base64 >/dev/null 2>&1; test -w /tmp; test -f /opt/chaosatlas/{capability}-extension-capability; test ! -e {_CONTROL_PATH}"
        code, stdout, stderr = self._run(["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", script])
        return {"status": "ready" if code == 0 else "blocked", "pod": pod, "read_only": True, "reason": None if code == 0 else (stderr or stdout).strip() or f"capability probe exited {code}"}

    def __call__(self, manifest: dict[str, Any], phase: dict[str, Any] | None = None, fault: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = manifest.get("metadata") if isinstance(manifest, dict) else {}
        spec = manifest.get("spec") if isinstance(manifest, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        spec = spec if isinstance(spec, dict) else {}
        family = str(spec.get("faultFamily") or "")
        result: dict[str, Any] = {"schema_version": "chaosatlas-native-extension-lifecycle-v1", "fault_family": family, "status": "blocked", "errors": [], "lifecycle": ["preflight"], "injection": {"applied": False, "confirmed": False}, "recovery": {"confirmed": False}, "cleanup": {"confirmed": False}}
        if manifest.get("kind") != "ChaosAtlasNativeExtension" or family not in _FAMILIES:
            result["status"] = "method_invalid"
            result["errors"].append("native extension executor requires a supported ChaosAtlasNativeExtension")
            return self._finalize(result)
        if str(metadata.get("namespace") or "") != self.namespace or self.namespace not in self.allowed_namespaces:
            result["status"] = "environment_blocked"
            result["errors"].append("mutation namespace is outside the allow-list")
            return self._finalize(result)
        if not self.allow_live or not self.isolated:
            result["status"] = "environment_blocked"
            result["errors"].append("isolated live approval is required for native extensions")
            return self._finalize(result)
        if self.probe is None:
            result["status"] = "method_invalid"
            result["errors"].append("business probe is required")
            return self._finalize(result)
        selector = spec.get("targetSelector") if isinstance(spec.get("targetSelector"), dict) else self.target_selector
        selector = {str(key): str(value) for key, value in selector.items() if str(key).strip() and str(value).strip()}
        if not selector:
            result["status"] = "method_invalid"
            result["errors"].append("targetSelector is required")
            return self._finalize(result)
        try:
            mutation = build_native_extension_mutation(family, spec.get("parameters"))
        except (TypeError, ValueError) as exc:
            result["status"] = "method_invalid"
            result["errors"].append(str(exc))
            return self._finalize(result)
        pod, pod_error = self._target_pod(selector)
        if pod is None:
            result["status"] = "environment_blocked"
            result["errors"].append(pod_error or "target pod unavailable")
            return self._finalize(result)
        try:
            capabilities = self.capability_probe(pod, family)
        except TypeError:
            capabilities = self.capability_probe(pod)  # type: ignore[call-arg]
        except Exception as exc:
            capabilities = {"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}
        result.update({"target": {"kind": "Pod", "name": pod, "namespace": self.namespace}, "capabilities": capabilities, "control": {"path": mutation["control_path"], "control_sha256": hashlib.sha256(json.dumps(mutation["control"], sort_keys=True).encode()).hexdigest()}})
        if not isinstance(capabilities, dict) or capabilities.get("status") != "ready":
            result["status"] = "environment_blocked"
            result["errors"].append(f"capability probe blocked: {(capabilities or {}).get('reason') or 'probe failed'}")
            return self._finalize(result)
        result["baseline"] = self.probe("baseline")
        result["lifecycle"].append("baseline")
        if result["baseline"].get("status") != "pass":
            result["status"] = "business_not_reachable"
            result["errors"].append("independent business baseline did not pass")
            return self._finalize(result)
        encoded = base64.b64encode(json.dumps(mutation["control"], sort_keys=True, separators=(",", ":")).encode()).decode("ascii")
        command = ["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", f"printf '%s' '{encoded}' | base64 -d > {_CONTROL_PATH}"]
        applied = False
        try:
            code, stdout, stderr = self._run(command)
            result["injection"]["apply"] = {"return_code": code, "stdout": stdout, "stderr": stderr}
            if code != 0:
                result["status"] = "apply_failed"
                result["errors"].append((stderr or stdout).strip() or "native extension control write failed")
                return self._finalize(result)
            applied = True
            result["injection"].update({"applied": True, "confirmed": True})
            result["lifecycle"].append("inject")
            result["observation"] = self.probe("observe")
            result["lifecycle"].append("observe")
            result["status"] = "executed"
        finally:
            if applied:
                cleanup_code, cleanup_stdout, cleanup_stderr = self._run(["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", f"rm -f -- {_CONTROL_PATH}"])
                verify_code, verify_stdout, verify_stderr = self._run(["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", f"test ! -e {_CONTROL_PATH}"])
                verified = cleanup_code == 0 and verify_code == 0
                result["cleanup"] = {"confirmed": verified, "verified": verified, "cleanup_command": {"return_code": cleanup_code, "stdout": cleanup_stdout, "stderr": cleanup_stderr}, "verification": {"return_code": verify_code, "stdout": verify_stdout, "stderr": verify_stderr}}
                result["recovery"] = {"confirmed": False, "state": {"control_removed": verified}}
                if verified:
                    result["recovery"]["business_probe"] = self.probe("recovery")
                    result["recovery"]["confirmed"] = result["recovery"]["business_probe"].get("status") == "pass"
                result["lifecycle"].extend(["recover", "cleanup"])
                if not verified:
                    result["status"] = "cleanup_unverified"
                elif not result["recovery"]["confirmed"]:
                    result["status"] = "recovery_unconfirmed"
        return self._finalize(result)

    @staticmethod
    def _finalize(result: dict[str, Any]) -> dict[str, Any]:
        baseline = isinstance(result.get("baseline"), dict) and result["baseline"].get("status") == "pass"
        observation = result.get("observation") if isinstance(result.get("observation"), dict) else {}
        observed = observation.get("status") in {"pass", "degraded", "business_unreachable"}
        injection = bool((result.get("injection") or {}).get("confirmed"))
        recovery = bool((result.get("recovery") or {}).get("confirmed"))
        cleanup = bool((result.get("cleanup") or {}).get("confirmed"))
        comparison = all((baseline, injection, recovery, cleanup, observed)) and bool(observation.get("samples"))
        attestation = validate_attestation({"baseline": baseline, "injection": injection, "observation": observed, "recovery": recovery, "cleanup": cleanup, "independent_oracle": baseline and observed, "comparison_eligible": comparison})
        result["attestation"] = {"schema_version": "chaosatlas-runtime-result-v1", "valid": attestation.valid, "missing": list(attestation.missing), "comparison_eligible": comparison, "baseline": baseline, "injection": injection, "observation": observed, "recovery": recovery, "cleanup": cleanup, "independent_oracle": baseline and observed}
        result.update({"outcome_status": "observed" if observation.get("status") == "pass" else str(observation.get("status") or result.get("status")), "injection_confirmed": injection, "injected_count": 1 if injection else 0, "recovery_confirmed": recovery, "cleanup_confirmed": cleanup, "promotion_allowed": attestation.valid, "verdict": observation_verdict(observation, result.get("status"), result.get("outcome_status"))})
        return result
