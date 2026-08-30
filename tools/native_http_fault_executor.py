"""Guarded native executor for HTTP rate-limit and dependency faults.

The target workload must expose the ChaosAtlas HTTP boundary control contract:
``/tmp/chaosatlas-http-control.json`` is read by the workload and removed by
the executor after the observation window. No generic container is treated as
supporting this contract without an explicit capability probe.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Callable

from tools.fault_executor import validate_attestation


Runner = Callable[..., tuple[int, str, str]]
_FAMILIES = {"http_rate_limit", "business_dependency_unreachable"}


def build_native_http_mutation(
    fault_family: str, parameters: dict[str, Any] | None = None
) -> dict[str, Any]:
    family = str(fault_family or "").strip()
    params = parameters if isinstance(parameters, dict) else {}
    if family not in _FAMILIES:
        raise ValueError(f"unsupported native HTTP fault family: {family}")
    if family == "business_dependency_unreachable":
        if params and set(params) != {"port", "path"}:
            raise ValueError("business_dependency_unreachable accepts optional port and path")
        if params:
            _validate_route(params)
        control = {"mode": "dependency_unreachable"}
        if params:
            control.update({"port": params["port"], "path": params["path"]})
    else:
        required = {"requests_per_window", "window_s", "status_code"}
        if set(params) not in (required, required | {"port", "path"}):
            raise ValueError(
                "http_rate_limit requires requests_per_window, window_s and status_code"
            )
        requests = params["requests_per_window"]
        window = params["window_s"]
        status_code = params["status_code"]
        if (
            isinstance(requests, bool)
            or not isinstance(requests, int)
            or not 1 <= requests <= 1000
        ):
            raise ValueError("requests_per_window must be in [1, 1000]")
        if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= 60:
            raise ValueError("window_s must be in [1, 60]")
        if isinstance(status_code, bool) or not isinstance(status_code, int) or not 429 <= status_code <= 429:
            raise ValueError("http_rate_limit status_code must be 429")
        control = {
            "mode": "rate_limit",
            "requests_per_window": requests,
            "window_s": window,
            "status_code": status_code,
        }
        if "port" in params:
            _validate_route(params)
            control.update({"port": params["port"], "path": params["path"]})
    encoded = base64.b64encode(
        json.dumps(control, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    path = "/tmp/chaosatlas-http-control.json"
    return {
        "fault_family": family,
        "parameters": dict(params),
        "control": control,
        "command": ["sh", "-ceu", f"printf '%s' '{encoded}' | base64 -d > {path}"],
        "cleanup_command": ["sh", "-ceu", f"rm -f -- {path}"],
        "control_path": path,
    }


def _validate_route(params: dict[str, Any]) -> None:
    port = params.get("port")
    path = str(params.get("path") or "")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 or not path.startswith("/"):
        raise ValueError("native HTTP route requires port in [1, 65535] and an absolute path")


class NativeHttpFaultExecutor:
    """Execute one workload-local HTTP boundary mutation with full attestation."""

    def __init__(
        self,
        *,
        namespace: str,
        allowed_namespaces: set[str],
        allow_live: bool = False,
        isolated: bool = False,
        runner: Runner | None = None,
        probe: Callable[[str], dict[str, Any]] | None = None,
        capability_probe: Callable[[str], dict[str, Any]] | None = None,
        target_selector: dict[str, str] | None = None,
    ) -> None:
        self.namespace = str(namespace or "").strip()
        self.allowed_namespaces = {str(item).strip() for item in allowed_namespaces if str(item).strip()}
        self.allow_live = bool(allow_live)
        self.isolated = bool(isolated)
        self.runner = runner
        self.probe = probe
        self.capability_probe = capability_probe or self._default_capability_probe
        self.target_selector = {
            str(key): str(value)
            for key, value in (target_selector or {}).items()
            if str(key).strip() and str(value).strip()
        }

    def _run(self, args: list[str], timeout: int = 45) -> tuple[int, str, str]:
        if self.runner is None:
            raise RuntimeError("native HTTP runner is not configured")
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

    def _default_capability_probe(self, pod: str) -> dict[str, Any]:
        path = "/tmp/chaosatlas-http-control.json"
        script = f"set -eu; command -v sh >/dev/null 2>&1; command -v base64 >/dev/null 2>&1; test -w /tmp; test -f /opt/chaosatlas/http-boundary-capability; test ! -e {path}"
        try:
            code, stdout, stderr = self._run(["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", script])
        except (OSError, RuntimeError, TimeoutError) as exc:
            return {"status": "blocked", "pod": pod, "reason": str(exc)}
        return {
            "status": "ready" if code == 0 else "blocked",
            "pod": pod,
            "read_only": True,
            "reason": None if code == 0 else (stderr or stdout).strip() or f"capability probe exited {code}",
        }

    def __call__(
        self,
        manifest: dict[str, Any],
        phase: dict[str, Any] | None = None,
        fault: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = manifest.get("metadata") if isinstance(manifest, dict) else {}
        spec = manifest.get("spec") if isinstance(manifest, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        spec = spec if isinstance(spec, dict) else {}
        family = str(spec.get("faultFamily") or "")
        base = {
            "schema_version": "chaosatlas-native-http-lifecycle-v1",
            "fault_family": family,
            "status": "blocked",
            "errors": [],
        }
        if manifest.get("kind") != "ChaosAtlasNativeHttpFault" or family not in _FAMILIES:
            return {**base, "status": "method_invalid", "errors": ["native HTTP executor requires a supported ChaosAtlasNativeHttpFault"]}
        if str(metadata.get("namespace") or "") != self.namespace or self.namespace not in self.allowed_namespaces:
            return {**base, "status": "environment_blocked", "errors": ["mutation namespace is outside the allow-list"]}
        if not self.allow_live or not self.isolated:
            return {**base, "status": "environment_blocked", "errors": ["isolated live approval is required for native HTTP faults"]}
        if self.probe is None:
            return {**base, "status": "method_invalid", "errors": ["business probe is required"]}
        selector = spec.get("targetSelector") if isinstance(spec.get("targetSelector"), dict) else self.target_selector
        selector = {str(key): str(value) for key, value in selector.items() if str(key).strip() and str(value).strip()}
        if not selector:
            return {**base, "status": "method_invalid", "errors": ["targetSelector is required"]}
        try:
            mutation = build_native_http_mutation(family, spec.get("parameters"))
        except (TypeError, ValueError) as exc:
            return {**base, "status": "method_invalid", "errors": [str(exc)]}
        pod, pod_error = self._target_pod(selector)
        if pod is None:
            return {**base, "status": "environment_blocked", "errors": [pod_error or "target pod unavailable"]}
        try:
            capabilities = self.capability_probe(pod)
        except Exception as exc:
            capabilities = {"status": "blocked", "pod": pod, "reason": f"{type(exc).__name__}: {exc}"}
        if not isinstance(capabilities, dict) or capabilities.get("status") != "ready":
            return {**base, "status": "environment_blocked", "target": {"kind": "Pod", "name": pod, "namespace": self.namespace}, "capabilities": capabilities, "errors": [f"capability probe blocked: {(capabilities or {}).get('reason') or 'probe failed'}"]}
        encoded = mutation["command"][-1].split("'", 2)[1]
        command = ["exec", pod, "-n", self.namespace, "--", *mutation["command"]]
        cleanup_command = ["exec", pod, "-n", self.namespace, "--", *mutation["cleanup_command"]]
        baseline = self.probe("baseline")
        result: dict[str, Any] = {
            **base,
            "target": {"kind": "Pod", "name": pod, "namespace": self.namespace},
            "capabilities": capabilities,
            "baseline": baseline,
            "injection": {"applied": False, "confirmed": False},
            "observation": None,
            "recovery": {"confirmed": False},
            "cleanup": {"confirmed": False},
            "control": {"path": mutation["control_path"], "encoded_sha256": hashlib.sha256(encoded.encode()).hexdigest()},
        }
        if baseline.get("status") != "pass":
            result["status"] = "business_not_reachable"
            result["errors"].append("independent business baseline did not pass")
            return self._finalize(result)
        applied = False
        try:
            code, stdout, stderr = self._run(command)
            result["injection"]["apply"] = {"return_code": code, "stdout": stdout, "stderr": stderr}
            if code != 0:
                result["status"] = "apply_failed"
                result["errors"].append((stderr or stdout).strip() or "native HTTP control write failed")
                return self._finalize(result)
            applied = True
            result["injection"].update({"applied": True, "confirmed": True})
            result["observation"] = self.probe("observe")
            result["recovery"] = {"confirmed": False, "state": {"control_removed": False}}
            result["status"] = "executed"
        finally:
            if applied:
                code, stdout, stderr = self._run(cleanup_command)
                verify_code, verify_stdout, verify_stderr = self._run(["exec", pod, "-n", self.namespace, "--", "sh", "-ceu", f"test ! -e {mutation['control_path']}"])
                verified = code == 0 and verify_code == 0
                result["cleanup"] = {"confirmed": verified, "verified": verified, "cleanup_command": {"return_code": code, "stdout": stdout, "stderr": stderr}, "verification": {"return_code": verify_code, "stdout": verify_stdout, "stderr": verify_stderr}}
                result["recovery"]["state"]["control_removed"] = verified
                if verified:
                    try:
                        recovery_probe = self.probe("recovery")
                    except Exception as exc:
                        recovery_probe = {"status": "unavailable", "samples": [], "reason": f"{type(exc).__name__}: {exc}"}
                    result["recovery"]["business_probe"] = recovery_probe
                    result["recovery"]["confirmed"] = recovery_probe.get("status") == "pass"
                if not verified:
                    result["status"] = "cleanup_unverified"
                elif not result["recovery"].get("confirmed"):
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
        family = str(result.get("fault_family") or "")
        samples = observation.get("samples") if isinstance(observation.get("samples"), list) else []
        status_codes = {
            item.get("status_code")
            for item in samples
            if isinstance(item, dict) and isinstance(item.get("status_code"), int)
        }
        if family == "http_rate_limit" and 429 in status_codes:
            outcome_status = "rate_limit_observed"
            observation_contract = {
                "kind": "http_rate_limit",
                "threshold_status": 429,
                "observed_status_codes": sorted(status_codes),
                "threshold_reached": True,
            }
        elif family == "business_dependency_unreachable" and 503 in status_codes:
            outcome_status = "dependency_unreachable_observed"
            observation_contract = {
                "kind": "business_dependency_unreachable",
                "dependency_status": 503,
                "observed_status_codes": sorted(status_codes),
                "dependency_unreachable": True,
            }
        else:
            outcome_status = "observed" if observation.get("status") == "pass" else str(observation.get("status") or result.get("status"))
            observation_contract = {"kind": family or "native_http", "observed_status_codes": sorted(status_codes)}
        result["observation_contract"] = observation_contract
        comparison = all((baseline, injection, recovery, cleanup, observed)) and bool(observation.get("samples")) and (
            observation.get("status") in {"pass", "degraded"} or outcome_status in {"rate_limit_observed", "dependency_unreachable_observed"}
        )
        attestation = validate_attestation({"baseline": baseline, "injection": injection, "observation": observed, "recovery": recovery, "cleanup": cleanup, "independent_oracle": baseline and observed, "comparison_eligible": comparison})
        result["attestation"] = {"schema_version": "chaosatlas-runtime-result-v1", "valid": attestation.valid, "missing": list(attestation.missing), "comparison_eligible": comparison, "baseline": baseline, "injection": injection, "observation": observed, "recovery": recovery, "cleanup": cleanup, "independent_oracle": baseline and observed}
        result.update({"outcome_status": outcome_status, "injection_confirmed": injection, "injected_count": 1 if injection else 0, "recovery_confirmed": recovery, "cleanup_confirmed": cleanup, "promotion_allowed": attestation.valid, "verdict": "observation_pending" if result.get("status") == "executed" else result.get("status")})
        return result
