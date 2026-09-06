"""Namespace-scoped executor for reversible Kubernetes API fault intents."""

from __future__ import annotations

import copy
import base64
import hashlib
import json
import time
from typing import Any, Callable

from tools.fault_executor import observation_verdict, validate_attestation
from tools.run_chaos_experiment import run_kubectl


Runner = Callable[..., tuple[int, str, str]]
Probe = Callable[[str], dict[str, Any]]


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _annotations(snapshot: dict[str, Any]) -> dict[str, str]:
    value = ((snapshot.get("spec") or {}).get("template") or {}).get("metadata") or {}
    annotations = value.get("annotations")
    return {str(key): str(item) for key, item in annotations.items()} if isinstance(annotations, dict) else {}


def _containers(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    template = ((snapshot.get("spec") or {}).get("template") or {})
    pod_spec = template.get("spec") if isinstance(template, dict) else {}
    values = pod_spec.get("containers") if isinstance(pod_spec, dict) else []
    return copy.deepcopy(values) if isinstance(values, list) else []


def _deployment_template_patch(containers: list[dict[str, Any]]) -> dict[str, Any]:
    return {"spec": {"template": {"spec": {"containers": containers}}}}


def _restorable_view(value: dict[str, Any], kind: str) -> dict[str, Any]:
    """Ignore server-managed metadata while verifying the restored object."""
    if kind.lower() == "secret":
        return {key: copy.deepcopy(value.get(key)) for key in ("data", "stringData", "type") if key in value}
    spec = value.get("spec") if isinstance(value.get("spec"), dict) else {}
    return {"spec": copy.deepcopy(spec)}


def _contains_subset(value: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(value, dict) and all(
            key in value and _contains_subset(value[key], item) for key, item in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(value, list) and value == expected
    return value == expected


def build_mutation(fault_family: str, snapshot: dict[str, Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one reversible merge patch from an immutable Deployment snapshot."""

    if not isinstance(snapshot, dict):
        raise ValueError("deployment snapshot must be an object")
    family = str(fault_family or "").strip()
    params = parameters if isinstance(parameters, dict) else {}
    snapshot_copy = copy.deepcopy(snapshot)
    if family == "secret_rotation":
        if str((snapshot.get("kind") or "Secret")) != "Secret":
            raise ValueError("secret_rotation requires a Secret snapshot")
        key = str(params.get("key") or "").strip()
        value = str(params.get("value") or "")
        if not key or not value:
            raise ValueError("secret_rotation requires non-empty key and value")
        if not value.startswith("chaosatlas-test-"):
            raise ValueError("secret_rotation value must be a generated test placeholder")
        data = snapshot_copy.get("data") if isinstance(snapshot_copy.get("data"), dict) else {}
        patch = {"data": {key: base64.b64encode(value.encode("utf-8")).decode("ascii")}}
        restore_data = {str(item): str(encoded) for item, encoded in data.items()}
        restore = {"data": restore_data} if restore_data else {"data": None}
        return {
            "fault_family": family,
            "snapshot": snapshot_copy,
            "snapshot_sha256": _hash(snapshot_copy),
            "patch": patch,
            "restore_patch": restore,
            "changed_path": f"/data/{key}",
            "evidence_parameters": {"key": key, "value_redacted": True},
        }
    original = (snapshot.get("spec") or {}).get("replicas")
    if family == "replica_reduction":
        if isinstance(original, bool) or not isinstance(original, int) or original < 1:
            raise ValueError("deployment snapshot requires replicas >= 1")
        target = params.get("replicas", original - 1)
        if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < original:
            raise ValueError("replica_reduction replicas must be an integer below the original count")
        return {
            "fault_family": family,
            "snapshot": snapshot_copy,
            "snapshot_sha256": _hash(snapshot_copy),
            "patch": {"spec": {"replicas": target}},
            "restore_patch": {"spec": {"replicas": original}},
            "changed_path": "/spec/replicas",
        }
    if family in {"config_reload", "config_drift"}:
        annotations = _annotations(snapshot_copy)
        if family == "config_reload":
            token = str(params.get("reload_token") or "").strip()
            if not token:
                token = _hash(snapshot_copy)[:16]
            key = "chaosatlas.dev/reload-token"
            value = token
        else:
            value = str(params.get("value") or "").strip()
            if not value:
                raise ValueError("config drift value must be non-empty")
            key = "chaosatlas.dev/config-drift"
        changed = {**annotations, key: value}
        # Merge patches do not remove keys omitted from an object. Explicitly
        # send null for a test annotation that was absent in the snapshot.
        restore = dict(annotations)
        if key not in annotations:
            restore[key] = None
        return {
            "fault_family": family,
            "snapshot": snapshot_copy,
            "snapshot_sha256": _hash(snapshot_copy),
            "patch": {"spec": {"template": {"metadata": {"annotations": changed}}}},
            "restore_patch": {"spec": {"template": {"metadata": {"annotations": restore}}}},
            "changed_path": f"/spec/template/metadata/annotations/{key}",
        }
    if family in {"env_misconfiguration", "image_pull_failure"}:
        containers = _containers(snapshot_copy)
        if not containers:
            raise ValueError(f"{family} requires at least one container")
        target_name = str(params.get("container") or "").strip()
        index = next((i for i, item in enumerate(containers) if not target_name or str(item.get("name") or "") == target_name), None)
        if index is None:
            raise ValueError("target container was not found")
        original_containers = copy.deepcopy(containers)
        if family == "image_pull_failure":
            image = str(params.get("image") or "").strip()
            if not image:
                raise ValueError("image_pull_failure requires non-empty image")
            containers[index]["image"] = image
            changed_path = f"/spec/template/spec/containers/{index}/image"
        else:
            env_name = str(params.get("name") or "").strip()
            env_value = str(params.get("value") or "")
            if not env_name or not env_value:
                raise ValueError("env_misconfiguration requires non-empty name and value")
            env = containers[index].get("env") if isinstance(containers[index].get("env"), list) else []
            env = copy.deepcopy(env)
            existing = next((item for item in env if isinstance(item, dict) and item.get("name") == env_name), None)
            if existing is None:
                env.append({"name": env_name, "value": env_value})
            else:
                existing.pop("valueFrom", None)
                existing["value"] = env_value
            containers[index]["env"] = env
            changed_path = f"/spec/template/spec/containers/{index}/env/{env_name}"
        return {
            "fault_family": family,
            "snapshot": snapshot_copy,
            "snapshot_sha256": _hash(snapshot_copy),
            "patch": _deployment_template_patch(containers),
            "restore_patch": _deployment_template_patch(original_containers),
            "changed_path": changed_path,
            "evidence_parameters": {key: value for key, value in params.items() if key != "value"},
        }
    if family == "rollout_pause":
        paused = params.get("paused")
        if not isinstance(paused, bool):
            raise ValueError("rollout_pause requires boolean paused")
        original_paused = (snapshot_copy.get("spec") or {}).get("paused")
        return {
            "fault_family": family,
            "snapshot": snapshot_copy,
            "snapshot_sha256": _hash(snapshot_copy),
            "patch": {"spec": {"paused": paused}},
            "restore_patch": {"spec": {"paused": original_paused if isinstance(original_paused, bool) else None}},
            "changed_path": "/spec/paused",
        }
    if family == "pod_unschedulable":
        key = str(params.get("node_selector_key") or "").strip()
        value = str(params.get("node_selector_value") or "").strip()
        if not key or not value:
            raise ValueError("pod_unschedulable requires node selector key and value")
        template = ((snapshot_copy.get("spec") or {}).get("template") or {})
        pod_spec = template.get("spec") if isinstance(template, dict) else {}
        original_selector = copy.deepcopy(pod_spec.get("nodeSelector")) if isinstance(pod_spec, dict) else None
        selector = dict(original_selector) if isinstance(original_selector, dict) else {}
        selector[key] = value
        return {
            "fault_family": family,
            "snapshot": snapshot_copy,
            "snapshot_sha256": _hash(snapshot_copy),
            "patch": {"spec": {"template": {"spec": {"nodeSelector": selector}}}},
            "restore_patch": {"spec": {"template": {"spec": {"nodeSelector": original_selector if original_selector else None}}}},
            "changed_path": f"/spec/template/spec/nodeSelector/{key}",
            "evidence_parameters": {"node_selector_key": key, "node_selector_value": value},
        }
    raise ValueError(f"unsupported Kubernetes API fault family: {family}")


class KubernetesApiFaultExecutor:
    """Execute and restore one Kubernetes API mutation under explicit gates."""

    def __init__(
        self,
        *,
        namespace: str,
        allowed_namespaces: set[str],
        allow_live: bool = False,
        runner: Runner | None = None,
        probe: Probe | None = None,
        kube_context: str | None = None,
        isolated: bool = False,
        disposable_cluster: bool = False,
        injection_timeout: float = 60,
        poll_interval: float = 1,
    ) -> None:
        self.namespace = str(namespace or "").strip()
        self.allowed_namespaces = {str(item).strip() for item in allowed_namespaces if str(item).strip()}
        self.allow_live = bool(allow_live)
        self.runner = runner or run_kubectl
        self.probe = probe
        self.kube_context = str(kube_context).strip() if kube_context else None
        self.isolated = bool(isolated)
        self.disposable_cluster = bool(disposable_cluster)
        self.injection_timeout = max(0.0, float(injection_timeout))
        self.poll_interval = max(0.0, float(poll_interval))

    def _run(self, args: list[str], timeout: int = 30) -> tuple[int, str, str]:
        try:
            return self.runner(args, timeout=timeout, kube_context=self.kube_context)
        except TypeError:
            return self.runner(args, timeout=timeout)

    def _get(self, kind: str, name: str) -> tuple[dict[str, Any] | None, str | None]:
        resource = {"secret": "secret", "deployment": "deployment", "statefulset": "statefulset", "daemonset": "daemonset"}.get(kind.lower())
        if resource is None:
            return None, f"unsupported Kubernetes target kind: {kind}"
        code, stdout, stderr = self._run(["get", resource, name, "-n", self.namespace, "-o", "json"])
        if code != 0:
            return None, (stderr or stdout).strip() or f"kubectl exit {code}"
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return None, f"invalid deployment JSON: {exc}"
        return value if isinstance(value, dict) else None, None

    def _patch(self, kind: str, name: str, patch: dict[str, Any]) -> tuple[int, str, str]:
        resource = {"secret": "secret", "deployment": "deployment", "statefulset": "statefulset", "daemonset": "daemonset"}.get(kind.lower())
        if resource is None:
            return 1, "", f"unsupported Kubernetes target kind: {kind}"
        return self._run(["patch", resource, name, "-n", self.namespace, "--type=merge", "-p", json.dumps(patch, separators=(",", ":"))])

    def _pods(self, snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        selector = ((snapshot.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
        if not isinstance(selector, dict) or not selector:
            return [], "workload selector is unavailable"
        label = ",".join(f"{key}={value}" for key, value in sorted(selector.items()))
        code, stdout, stderr = self._run(["get", "pods", "-n", self.namespace, "-l", label, "-o", "json"])
        if code != 0:
            return [], (stderr or stdout).strip() or f"kubectl exit {code}"
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return [], f"invalid Pod JSON: {exc}"
        return [item for item in value.get("items") or [] if isinstance(item, dict)], None

    def _confirm_injection(
        self,
        family: str,
        target_kind: str,
        name: str,
        snapshot: dict[str, Any],
        mutation: dict[str, Any],
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.injection_timeout
        attempts = 0
        last_error: str | None = None
        observed_reasons: set[str] = set()
        while True:
            attempts += 1
            current, error = self._get(target_kind, name)
            if error or current is None:
                last_error = error or "mutated target is unavailable"
            elif family == "secret_rotation":
                key = str((mutation.get("evidence_parameters") or {}).get("key") or "")
                expected = ((mutation.get("patch") or {}).get("data") or {}).get(key)
                actual = (current.get("data") or {}).get(key)
                if key and expected and actual == expected:
                    return {"confirmed": True, "attempts": attempts, "mechanism": "secret_value_reflected"}
                last_error = "rotated Secret key was not reflected"
            elif family in {"image_pull_failure", "pod_unschedulable"}:
                pods, pod_error = self._pods(snapshot)
                if pod_error:
                    last_error = pod_error
                elif family == "image_pull_failure":
                    expected_image = str(((mutation.get("evidence_parameters") or {}).get("image")) or "")
                    for pod in pods:
                        images = {str(item.get("image") or "") for item in (pod.get("spec") or {}).get("containers") or []}
                        for status in (pod.get("status") or {}).get("containerStatuses") or []:
                            waiting = ((status.get("state") or {}).get("waiting") or {}) if isinstance(status, dict) else {}
                            reason = str(waiting.get("reason") or "")
                            if reason:
                                observed_reasons.add(reason)
                            if expected_image in images and reason in {"ErrImagePull", "ImagePullBackOff"}:
                                return {"confirmed": True, "attempts": attempts, "mechanism": "pod_image_pull_waiting", "observed_reasons": sorted(observed_reasons)}
                    last_error = "no target Pod reached ErrImagePull or ImagePullBackOff"
                else:
                    params = mutation.get("evidence_parameters") or {}
                    key = str(params.get("node_selector_key") or "")
                    expected_value = str(params.get("node_selector_value") or "")
                    for pod in pods:
                        selector = (pod.get("spec") or {}).get("nodeSelector") or {}
                        for condition in (pod.get("status") or {}).get("conditions") or []:
                            reason = str(condition.get("reason") or "")
                            if reason:
                                observed_reasons.add(reason)
                            if selector.get(key) == expected_value and condition.get("type") == "PodScheduled" and condition.get("status") == "False" and reason == "Unschedulable":
                                return {"confirmed": True, "attempts": attempts, "mechanism": "pod_scheduling_condition", "observed_reasons": sorted(observed_reasons)}
                    last_error = "no target Pod reached the Unschedulable condition"
            elif _contains_subset(current, mutation.get("patch") or {}):
                return {"confirmed": True, "attempts": attempts, "mechanism": "api_state_reflected"}
            else:
                last_error = "mutated API state was not reflected"
            if time.monotonic() >= deadline:
                return {"confirmed": False, "attempts": attempts, "mechanism": "runtime_effect_required", "observed_reasons": sorted(observed_reasons), "error": last_error}
            time.sleep(self.poll_interval)

    def run(self, manifest: dict[str, Any], *, action_id: str = "kubernetes-api-fault", fault: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = manifest.get("metadata") if isinstance(manifest, dict) else {}
        spec = manifest.get("spec") if isinstance(manifest, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        spec = spec if isinstance(spec, dict) else {}
        namespace = str(metadata.get("namespace") or "")
        name = str((spec.get("targetRef") or {}).get("name") or "")
        target_kind = str((spec.get("targetRef") or {}).get("kind") or "Deployment")
        family = str(spec.get("faultFamily") or (fault or {}).get("kind") or "")
        base = {"schema_version": "chaosatlas-kubernetes-api-lifecycle-v1", "action_id": action_id, "fault_family": family, "status": "blocked", "lifecycle": ["preflight"], "errors": []}
        if manifest.get("kind") != "ChaosAtlasKubernetesFault":
            return {**base, "status": "method_invalid", "errors": ["Kubernetes API executor requires ChaosAtlasKubernetesFault"]}
        if not name or not family:
            return {**base, "status": "method_invalid", "errors": ["targetRef.name and faultFamily are required"]}
        if namespace != self.namespace or namespace not in self.allowed_namespaces:
            return {**base, "status": "environment_blocked", "errors": ["mutation namespace is outside the allow-list"]}
        owned_disposable_namespace = self.namespace.startswith(("chaosatlas-run-", "ca-l1-", "ca-l2-"))
        if family in {"pod_unschedulable", "image_pull_failure"} and (not self.isolated or not owned_disposable_namespace):
            return {**base, "status": "environment_blocked", "errors": [f"{family} requires a disposable isolated namespace"]}
        if family == "api_server_delay":
            return {**base, "status": "environment_blocked", "errors": ["api_server_delay requires a disposable cluster control-plane executor"]}
        if not self.allow_live:
            return {**base, "status": "environment_blocked", "errors": ["explicit live approval is required"]}
        if self.probe is None:
            return {**base, "status": "method_invalid", "errors": ["business probe is required"]}
        if family == "secret_rotation" and target_kind != "Secret":
            return {**base, "status": "method_invalid", "errors": ["secret_rotation targetRef.kind must be Secret"]}
        if family != "secret_rotation" and target_kind not in {"Deployment", "StatefulSet", "DaemonSet"}:
            return {**base, "status": "method_invalid", "errors": ["Kubernetes fault targetRef.kind must be Deployment, StatefulSet or DaemonSet"]}
        snapshot, error = self._get(target_kind, name)
        if snapshot is None:
            return {**base, "status": "environment_blocked", "errors": [error or "deployment snapshot unavailable"]}
        try:
            mutation = build_mutation(family, snapshot, spec.get("parameters"))
        except (TypeError, ValueError) as exc:
            return {**base, "status": "method_invalid", "errors": [str(exc)]}
        result = {
            **base,
            "target": {"kind": target_kind, "name": name, "namespace": namespace},
            "snapshot_sha256": mutation["snapshot_sha256"],
            "baseline": None,
            "injection": {"applied": False, "confirmed": False},
            "observation": None,
            "recovery": {"confirmed": False},
            "cleanup": {"confirmed": False},
        }
        baseline = self.probe("baseline")
        result["baseline"] = baseline
        result["lifecycle"].append("baseline")
        if baseline.get("status") != "pass":
            result["status"] = "business_not_reachable"
            result["errors"].append("independent business baseline did not pass")
            return self._finalize(result)
        applied = False
        try:
            code, stdout, stderr = self._patch(target_kind, name, mutation["patch"])
            result["injection"]["apply"] = {"return_code": code, "stdout": stdout, "stderr": stderr}
            if code != 0:
                result["status"] = "apply_failed"
                result["errors"].append((stderr or stdout).strip() or "kubectl patch failed")
                return self._finalize(result)
            applied = True
            confirmation = self._confirm_injection(family, target_kind, name, snapshot, mutation)
            result["injection"].update({"applied": True, "confirmed": confirmation["confirmed"], "confirmation": confirmation})
            result["lifecycle"].append("inject")
            if not confirmation["confirmed"]:
                result["status"] = "injection_not_confirmed"
                result["errors"].append(str(confirmation.get("error") or "runtime mutation effect was not confirmed"))
                return self._finalize(result)
            observed = self.probe("observe")
            result["observation"] = observed
            result["lifecycle"].append("observe")
            result["outcome_status"] = "observed" if observed.get("status") == "pass" else str(observed.get("status") or "observation_failed")
            result["status"] = "executed"
        finally:
            if applied:
                code, stdout, stderr = self._patch(target_kind, name, mutation["restore_patch"])
                restored, restore_error = self._get(target_kind, name)
                snapshot_match = restored is not None and _restorable_view(restored, target_kind) == _restorable_view(snapshot, target_kind)
                recovery_confirmed = code == 0 and snapshot_match
                try:
                    recovery_probe = self.probe("recovery") if recovery_confirmed else {"status": "not_run", "samples": []}
                except Exception as exc:
                    recovery_probe = {"status": "error", "samples": [], "error": f"{type(exc).__name__}: {exc}"}
                recovery_confirmed = recovery_confirmed and recovery_probe.get("status") == "pass"
                replicas_match = ((restored.get("spec") or {}).get("replicas") if restored else None) == ((snapshot.get("spec") or {}).get("replicas"))
                annotations_match = _annotations(restored) == _annotations(snapshot) if restored and target_kind == "Deployment" else snapshot_match
                result["recovery"] = {
                    "confirmed": recovery_confirmed,
                    "snapshot_match": snapshot_match,
                    "replicas_match": replicas_match,
                    "annotations_match": annotations_match,
                    "business_probe": recovery_probe,
                    "patch": {"return_code": code, "stdout": stdout, "stderr": stderr},
                }
                result["lifecycle"].append("recover")
                result["cleanup"] = {"confirmed": bool(result["recovery"]["confirmed"]), "verified": bool(result["recovery"]["confirmed"]), "error": restore_error}
                result["lifecycle"].append("cleanup")
                if not result["recovery"]["confirmed"]:
                    result["status"] = "recovery_timeout"
        return self._finalize(result)

    @staticmethod
    def _finalize(result: dict[str, Any]) -> dict[str, Any]:
        observation = result.get("observation") if isinstance(result.get("observation"), dict) else {}
        baseline_ok = isinstance(result.get("baseline"), dict) and result["baseline"].get("status") == "pass"
        observation_ok = observation.get("status") in {"pass", "degraded", "business_unreachable"}
        injection_ok = bool((result.get("injection") or {}).get("confirmed"))
        recovery_ok = bool((result.get("recovery") or {}).get("confirmed"))
        cleanup_ok = bool((result.get("cleanup") or {}).get("confirmed"))
        # A confirmed post-injection business outage is valid comparison
        # evidence when the baseline passed; it is classified as degradation
        # by the RCA projection rather than treated as a baseline failure.
        comparison_eligible = all((baseline_ok, injection_ok, observation_ok, recovery_ok, cleanup_ok)) and bool(observation.get("samples"))
        attestation = validate_attestation({"baseline": baseline_ok, "injection": injection_ok, "observation": observation_ok, "recovery": recovery_ok, "cleanup": cleanup_ok, "independent_oracle": baseline_ok and observation_ok, "comparison_eligible": comparison_eligible})
        result["attestation"] = {"schema_version": "chaosatlas-runtime-result-v1", "valid": attestation.valid, "missing": list(attestation.missing), "comparison_eligible": comparison_eligible, "baseline": baseline_ok, "injection": injection_ok, "observation": observation_ok, "recovery": recovery_ok, "cleanup": cleanup_ok, "independent_oracle": baseline_ok and observation_ok}
        result.update({"injection_confirmed": injection_ok, "injected_count": 1 if injection_ok else 0, "recovery_confirmed": recovery_ok, "cleanup_confirmed": cleanup_ok, "promotion_allowed": attestation.valid, "verdict": observation_verdict(observation, result.get("status"), result.get("outcome_status"))})
        return result

    def __call__(self, manifest: dict[str, Any], phase: dict[str, Any] | None = None, fault: dict[str, Any] | None = None) -> dict[str, Any]:
        action_id = str((manifest.get("metadata") or {}).get("name") or "kubernetes-api-fault")
        return self.run(manifest, action_id=action_id, fault=fault)


class ControlPlaneDelayExecutor:
    """Fail-closed adapter for API-server delay on disposable clusters only.

    Mutating the control plane cannot be represented by a namespace-scoped
    Kubernetes API patch.  A deployment-specific integration must provide the
    ``mutator`` callback, which owns cluster snapshot, delay, restore, and
    teardown.  Without it this executor records an auditable block.
    """

    def __init__(
        self,
        *,
        allow_live: bool = False,
        disposable_cluster: bool = False,
        mutator: Callable[..., dict[str, Any]] | None = None,
        probe: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.allow_live = bool(allow_live)
        self.disposable_cluster = bool(disposable_cluster)
        self.mutator = mutator
        self.probe = probe

    @staticmethod
    def _finalize(result: dict[str, Any]) -> dict[str, Any]:
        baseline = result.get("baseline") if isinstance(result.get("baseline"), dict) else {}
        observation = result.get("observation") if isinstance(result.get("observation"), dict) else {}
        injection = result.get("injection") if isinstance(result.get("injection"), dict) else {}
        recovery = result.get("recovery") if isinstance(result.get("recovery"), dict) else {}
        cleanup = result.get("cleanup") if isinstance(result.get("cleanup"), dict) else {}
        baseline_ok = baseline.get("status") == "pass"
        observation_ok = observation.get("status") in {"pass", "degraded", "business_unreachable"}
        injection_ok = bool(result.get("injection_confirmed") or injection.get("confirmed"))
        recovery_ok = bool(result.get("recovery_confirmed") or recovery.get("confirmed"))
        cleanup_ok = bool(result.get("cleanup_confirmed") or cleanup.get("confirmed"))
        comparison_eligible = all((baseline_ok, injection_ok, observation_ok, recovery_ok, cleanup_ok)) and bool(observation.get("samples"))
        attestation = validate_attestation({
            "baseline": baseline_ok,
            "injection": injection_ok,
            "observation": observation_ok,
            "recovery": recovery_ok,
            "cleanup": cleanup_ok,
            "independent_oracle": baseline_ok and observation_ok,
            "comparison_eligible": comparison_eligible,
        })
        result["lifecycle"] = list(dict.fromkeys(result.get("lifecycle") or ["preflight"]))
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
        result.update({
            "injection_confirmed": injection_ok,
            "injected_count": 1 if injection_ok else 0,
            "recovery_confirmed": recovery_ok,
            "cleanup_confirmed": cleanup_ok,
            "promotion_allowed": attestation.valid,
            "outcome_status": "observed" if observation.get("status") == "pass" else str(observation.get("status") or result.get("status")),
            "verdict": observation_verdict(result.get("observation"), result.get("status"), result.get("outcome_status")),
        })
        return result

    def __call__(self, manifest: dict[str, Any], **_: Any) -> dict[str, Any]:
        spec = manifest.get("spec") if isinstance(manifest, dict) else {}
        spec = spec if isinstance(spec, dict) else {}
        family = str(spec.get("faultFamily") or "")
        base = {
            "schema_version": "chaosatlas-control-plane-lifecycle-v1",
            "fault_family": family,
            "status": "environment_blocked",
            "injection_confirmed": False,
            "cleanup_confirmed": False,
            "errors": [],
        }
        if manifest.get("kind") != "ChaosAtlasControlPlaneFault" or family != "api_server_delay":
            return {**base, "status": "method_invalid", "errors": ["control-plane executor requires api_server_delay manifest"]}
        latency = (spec.get("parameters") or {}).get("latency_ms")
        if isinstance(latency, bool) or not isinstance(latency, int) or not 1 <= latency <= 300_000:
            return {**base, "status": "method_invalid", "errors": ["api_server_delay latency_ms must be in [1, 300000]"]}
        if not self.allow_live:
            return {**base, "errors": ["explicit live approval is required"]}
        if not self.disposable_cluster:
            return {**base, "errors": ["api_server_delay requires a disposable cluster"]}
        if self.mutator is None:
            return {**base, "errors": ["disposable control-plane mutator is not configured"]}
        if self.probe is None:
            return {**base, "status": "method_invalid", "errors": ["business probe is required for control-plane evidence"]}
        try:
            baseline = self.probe("baseline")
        except Exception as exc:
            return {**base, "status": "method_invalid", "errors": [f"business baseline probe failed: {type(exc).__name__}: {exc}"]}
        result: dict[str, Any] = {
            **base,
            "lifecycle": ["preflight", "baseline"],
            "baseline": baseline,
            "injection": {"applied": False, "confirmed": False},
            "observation": None,
            "recovery": {"confirmed": False},
            "cleanup": {"confirmed": False},
        }
        if not isinstance(baseline, dict) or baseline.get("status") != "pass":
            result["status"] = "business_not_reachable"
            result["errors"].append("independent business baseline did not pass")
            return self._finalize(result)
        try:
            value = self.mutator(latency_ms=latency, manifest=copy.deepcopy(manifest), probe=self.probe)
        except Exception as exc:
            result["status"] = "environment_blocked"
            result["errors"].append(f"control-plane mutator failed: {type(exc).__name__}: {exc}")
            return self._finalize(result)
        if not isinstance(value, dict):
            result["status"] = "method_invalid"
            result["errors"].append("control-plane mutator returned non-object")
            return self._finalize(result)
        result.update(value)
        result.setdefault("lifecycle", ["preflight", "baseline"])
        if result.get("injection_confirmed") or (result.get("injection") or {}).get("confirmed"):
            result["lifecycle"].append("inject")
        if result.get("observation") is not None:
            result["lifecycle"].append("observe")
        if result.get("recovery") is not None:
            result["lifecycle"].append("recover")
        if result.get("cleanup") is not None:
            result["lifecycle"].append("cleanup")
        return self._finalize(result)
