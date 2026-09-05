"""Guarded native resource-fault intent executor.

Resource exhaustion is intentionally disabled on shared clusters. The module
provides deterministic validation and an explicit isolation gate so a future
container runner can be added without changing the scenario contract.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from tools.fault_executor import observation_verdict, validate_attestation


Runner = Callable[[list[str]], tuple[int, str, str]]
_FAMILIES = {"disk_pressure", "file_descriptor_exhaustion", "process_exhaustion"}


def _safe_path(value: Any) -> str:
    path = str(value or "").strip()
    parts = path.split("/")
    if not path.startswith("/") or ".." in parts or path in {"/", ""}:
        raise ValueError("disk pressure path must be an absolute path without parent traversal")
    if not any(path == root or path.startswith(root + "/") for root in ("/tmp", "/var/tmp", "/dev/shm")):
        raise ValueError("disk pressure path must be under /tmp, /var/tmp or /dev/shm")
    return path


def build_native_mutation(fault_family: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    family = str(fault_family or "").strip()
    params = parameters if isinstance(parameters, dict) else {}
    if family not in _FAMILIES:
        raise ValueError(f"unsupported native resource fault family: {family}")
    if family == "disk_pressure":
        if set(params) != {"path", "size_mb"}:
            raise ValueError("disk_pressure requires path and size_mb")
        path = _safe_path(params.get("path"))
        size_mb = params.get("size_mb")
        if isinstance(size_mb, bool) or not isinstance(size_mb, int) or not 1 <= size_mb <= 1024:
            raise ValueError("disk_pressure size_mb must be in [1, 1024]")
        return {
            "fault_family": family,
            "parameters": {"path": path, "size_mb": size_mb},
            "command": [
                "sh",
                "-ceu",
                f"if command -v fallocate >/dev/null 2>&1; then fallocate -l {size_mb}M {path}; else dd if=/dev/zero of={path} bs=1M count={size_mb} status=none; fi",
            ],
            "cleanup_command": ["sh", "-ceu", f"rm -f -- {path}"],
        }
    if set(params) != {"count"}:
        raise ValueError(f"{family} requires count")
    count = params.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10000:
        raise ValueError(f"{family} count must be in [1, 10000]")
    if family == "file_descriptor_exhaustion":
        command = ["sh", "-ceu", f"i=0; while [ $i -lt {count} ]; do eval \"exec $i<>/dev/null\"; i=$((i+1)); done; sleep 30"]
        cleanup = ["sh", "-ceu", "true"]
    else:
        command = ["sh", "-ceu", f"i=0; while [ $i -lt {count} ]; do sleep 30 & i=$((i+1)); done; wait"]
        cleanup = ["sh", "-ceu", "true"]
    return {"fault_family": family, "parameters": {"count": count}, "command": command, "cleanup_command": cleanup}


class NativeResourceFaultExecutor:
    def __init__(self, *, namespace: str, allowed_namespaces: set[str], allow_live: bool = False, isolated: bool = False, runner: Runner | None = None, probe: Callable[[str], dict[str, Any]] | None = None, capability_probe: Callable[[str], dict[str, Any]] | None = None, target_selector: dict[str, str] | None = None) -> None:
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
            raise RuntimeError("native runner is not configured")
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
        items = payload.get("items") if isinstance(payload, dict) else None
        for item in items or []:
            metadata = item.get("metadata") if isinstance(item, dict) else {}
            status = item.get("status") if isinstance(item, dict) else {}
            if str((status or {}).get("phase") or "") == "Running" and (metadata or {}).get("name"):
                return str(metadata["name"]), None
        return None, "no Running target pod matched selector"

    def _default_capability_probe(self, pod: str, family: str) -> dict[str, Any]:
        shell = "bash" if family == "process_exhaustion" else "sh"
        checks = [
            f"command -v {shell} >/dev/null 2>&1",
            "command -v sleep >/dev/null 2>&1",
            "test -w /tmp",
        ]
        if family == "disk_pressure":
            checks.append("command -v fallocate >/dev/null 2>&1 || command -v dd >/dev/null 2>&1")
        if family == "disk_pressure":
            limit_check = "printf 'disk_write=available\\n'"
        else:
            limit_name = "open_files" if family == "file_descriptor_exhaustion" else "max_processes"
            limit_flag = "n" if family == "file_descriptor_exhaustion" else "u"
            limit_check = f"limit=$(ulimit -{limit_flag}); case \"$limit\" in ''|*[!0-9]*) [ \"$limit\" = unlimited ] || exit 1;; esac; printf '{limit_name}=%s\\n' \"$limit\""
        script = "set -eu; " + "; ".join(checks) + "; " + limit_check
        try:
            code, stdout, stderr = self._run(["exec", pod, "-n", self.namespace, "--", shell, "-ceu", script])
        except (OSError, RuntimeError, TimeoutError) as exc:
            return {"status": "blocked", "pod": pod, "reason": str(exc)}
        if code != 0:
            return {"status": "blocked", "pod": pod, "reason": (stderr or stdout).strip() or f"capability probe exited {code}"}
        limits: dict[str, str] = {}
        for line in (stdout or "").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                limits[key.strip()] = value.strip()
        return {"status": "ready", "pod": pod, "limits": limits, "read_only": True}

    def __call__(self, manifest: dict[str, Any], phase: dict[str, Any] | None = None, fault: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = manifest.get("metadata") if isinstance(manifest, dict) else {}
        spec = manifest.get("spec") if isinstance(manifest, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        spec = spec if isinstance(spec, dict) else {}
        family = str(spec.get("faultFamily") or "")
        base = {"schema_version": "chaosatlas-native-resource-lifecycle-v1", "fault_family": family, "status": "blocked", "errors": []}
        if manifest.get("kind") != "ChaosAtlasNativeFault" or family not in _FAMILIES:
            return {**base, "status": "method_invalid", "errors": ["native resource executor requires a supported ChaosAtlasNativeFault"]}
        if str(metadata.get("namespace") or "") != self.namespace or self.namespace not in self.allowed_namespaces:
            return {**base, "status": "environment_blocked", "errors": ["mutation namespace is outside the allow-list"]}
        if not self.allow_live or not self.isolated:
            return {**base, "status": "environment_blocked", "errors": ["isolated live approval is required for native resource faults"]}
        if self.probe is None:
            return {**base, "status": "method_invalid", "errors": ["business probe is required"]}
        selector = spec.get("targetSelector") if isinstance(spec.get("targetSelector"), dict) else self.target_selector
        selector = {str(key): str(value) for key, value in selector.items() if str(key).strip() and str(value).strip()}
        if not selector:
            return {**base, "status": "method_invalid", "errors": ["targetSelector is required"]}
        try:
            mutation = build_native_mutation(family, spec.get("parameters"))
        except (TypeError, ValueError) as exc:
            return {**base, "status": "method_invalid", "errors": [str(exc)]}
        pod, pod_error = self._target_pod(selector)
        if pod is None:
            return {**base, "status": "environment_blocked", "errors": [pod_error or "target pod unavailable"]}
        try:
            try:
                capabilities = self.capability_probe(pod, family)
            except TypeError:
                # Preserve compatibility with older injected probes that only
                # accepted the Pod name.
                capabilities = self.capability_probe(pod)
        except Exception as exc:
            capabilities = {"status": "blocked", "pod": pod, "reason": f"{type(exc).__name__}: {exc}"}
        if not isinstance(capabilities, dict) or capabilities.get("status") != "ready":
            reason = str((capabilities or {}).get("reason") or "native capability probe did not pass")
            return {**base, "status": "environment_blocked", "target": {"kind": "Pod", "name": pod, "namespace": self.namespace}, "capabilities": capabilities, "errors": [f"capability probe blocked: {reason}"]}
        marker = f"/tmp/chaosatlas-resource-{hashlib.sha256(json.dumps({'family': family, 'pod': pod, 'parameters': mutation['parameters']}, sort_keys=True).encode()).hexdigest()[:12]}"
        command = " ".join(json.dumps(str(item)) for item in mutation["command"])
        cleanup = " ".join(json.dumps(str(item)) for item in mutation["cleanup_command"])
        baseline = self.probe("baseline")
        result = {
            **base,
            "status": "blocked",
            "target": {"kind": "Pod", "name": pod, "namespace": self.namespace},
            "capabilities": capabilities,
            "baseline": baseline,
            "injection": {"applied": False, "confirmed": False},
            "observation": None,
            "recovery": {"confirmed": False},
            "cleanup": {"confirmed": False},
        }
        if baseline.get("status") != "pass":
            result["status"] = "business_not_reachable"
            result["errors"].append("independent business baseline did not pass")
            return self._finalize(result)
        applied = False
        try:
            start = f"( {command} ) >{marker}.log 2>&1 & echo $! >{marker}.pid"
            code, stdout, stderr = self._run(["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", start])
            result["injection"]["apply"] = {"return_code": code, "stdout": stdout, "stderr": stderr}
            if code != 0:
                result["status"] = "apply_failed"
                result["errors"].append((stderr or stdout).strip() or "native resource command failed")
                return self._finalize(result)
            applied = True
            result["injection"].update({"applied": True, "confirmed": True})
            result["lifecycle"] = ["preflight", "baseline", "inject"]
            result["observation"] = self.probe("observe")
            result["lifecycle"].append("observe")
            result["outcome_status"] = "observed" if result["observation"].get("status") == "pass" else str(result["observation"].get("status") or "observation_failed")
            result["status"] = "executed"
        finally:
            if applied:
                cleanup_script = f"kill $(cat {marker}.pid 2>/dev/null) 2>/dev/null || true; {cleanup}; rm -f {marker}.pid {marker}.log"
                code, stdout, stderr = self._run(["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", cleanup_script])
                result["recovery"] = {"confirmed": code == 0, "patch": {"return_code": code, "stdout": stdout, "stderr": stderr}}
                verify_code, verify_stdout, verify_stderr = self._run(
                    [
                        "exec",
                        pod,
                        "-n",
                        self.namespace,
                        "--",
                        "sh",
                        "-ceu",
                        f"test ! -e {marker}.pid && test ! -e {marker}.log",
                    ]
                )
                cleanup_verified = code == 0 and verify_code == 0
                result["cleanup"] = {
                    "confirmed": cleanup_verified,
                    "verified": cleanup_verified,
                    "cleanup_command": {"return_code": code, "stdout": stdout, "stderr": stderr},
                    "verification": {"return_code": verify_code, "stdout": verify_stdout, "stderr": verify_stderr},
                }
                result.setdefault("lifecycle", []).extend(["recover", "cleanup"])
                if code != 0:
                    result["status"] = "recovery_timeout"
                elif verify_code != 0:
                    result["status"] = "cleanup_unverified"
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
        result.update({"injection_confirmed": injection, "injected_count": 1 if injection else 0, "recovery_confirmed": recovery, "cleanup_confirmed": cleanup, "promotion_allowed": attestation.valid, "verdict": observation_verdict(observation, result.get("status"), result.get("outcome_status"))})
        return result
