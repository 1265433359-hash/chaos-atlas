"""Read-only Kubernetes project inventory and deterministic fault candidates."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from tools.deployment_capability import build_deployment_node, validate_deployment_node
from tools.extension_capability import generate_extension_candidates
from tools.dependency_fault_capability import normalize_declared_dependency_edges
from tools.fault_catalog import implemented_fault_families
from tools.fault_matrix import build_fault_matrix
from tools.parameterized_candidates import expand_candidates
from tools.recovery_contract import contract_for_fault


Runner = Callable[..., tuple[int, str, str]]
FAULT_FAMILIES = implemented_fault_families()


def _default_runner(args: list[str], timeout: int = 30, input_text: str | None = None) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["kubectl", *args],
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, "", str(exc)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _commit(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{40}", text):
        return text.lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:40]


def _metadata(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "name": str(source.get("name") or ""),
        "namespace": str(source.get("namespace") or ""),
        "labels": {str(key): str(item) for key, item in (source.get("labels") or {}).items()},
    }


def _safe_container(container: Any) -> dict[str, Any]:
    value = container if isinstance(container, dict) else {}
    output: dict[str, Any] = {"name": str(value.get("name") or "")}
    for key in ("resources", "readinessProbe", "livenessProbe", "startupProbe", "ports", "volumeMounts"):
        if isinstance(value.get(key), (dict, list)):
            output[key] = deepcopy(value[key])
    for key in ("image", "command", "args"):
        if isinstance(value.get(key), (str, list)):
            output[key] = deepcopy(value[key])
    return output


def _safe_deployment(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    spec = source.get("spec") if isinstance(source.get("spec"), dict) else {}
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    template_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    selector = spec.get("selector") if isinstance(spec.get("selector"), dict) else {}
    return {
        "metadata": _metadata(source.get("metadata")),
        "spec": {
            "replicas": int(spec.get("replicas") or 0),
            "selector": {"matchLabels": {str(key): str(item) for key, item in (selector.get("matchLabels") or {}).items()}},
            "template": {
                "metadata": {"labels": {str(key): str(item) for key, item in ((template.get("metadata") or {}).get("labels") or {}).items()}},
                "spec": {
                    "containers": [_safe_container(item) for item in (template_spec.get("containers") or [])],
                    "volumes": deepcopy(template_spec.get("volumes") or []),
                },
            },
        },
    }


def _safe_workload(value: Any, workload_kind: str) -> dict[str, Any]:
    normalized = _safe_deployment(value)
    normalized["workload_kind"] = workload_kind
    spec = value.get("spec") if isinstance(value, dict) and isinstance(value.get("spec"), dict) else {}
    normalized["spec"]["serviceName"] = str(spec.get("serviceName") or "")
    normalized["spec"]["volumeClaimTemplates"] = deepcopy(spec.get("volumeClaimTemplates") or [])
    return normalized


def _safe_resource_metadata(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return {"name": str(metadata.get("name") or ""), "namespace": str(metadata.get("namespace") or ""), "labels": {str(k): str(v) for k, v in (metadata.get("labels") or {}).items()}}


def _safe_persistent_volume_claim(value: Any) -> dict[str, Any]:
    result = _safe_resource_metadata(value)
    spec = value.get("spec") if isinstance(value, dict) and isinstance(value.get("spec"), dict) else {}
    status = value.get("status") if isinstance(value, dict) and isinstance(value.get("status"), dict) else {}
    result["spec"] = {"accessModes": deepcopy(spec.get("accessModes") or []), "storageClassName": str(spec.get("storageClassName") or ""), "resources": {"requests": deepcopy((spec.get("resources") or {}).get("requests") or {}) if isinstance(spec.get("resources"), dict) else {}}, "volumeMode": str(spec.get("volumeMode") or "")}
    result["status"] = {"phase": str(status.get("phase") or ""), "capacity": deepcopy(status.get("capacity") or {})}
    return result


def _safe_hpa(value: Any) -> dict[str, Any]:
    result = _safe_resource_metadata(value)
    spec = value.get("spec") if isinstance(value, dict) and isinstance(value.get("spec"), dict) else {}
    status = value.get("status") if isinstance(value, dict) and isinstance(value.get("status"), dict) else {}
    result["spec"] = {"scaleTargetRef": deepcopy(spec.get("scaleTargetRef") or {}), "minReplicas": spec.get("minReplicas"), "maxReplicas": spec.get("maxReplicas")}
    result["status"] = {"currentReplicas": status.get("currentReplicas"), "desiredReplicas": status.get("desiredReplicas")}
    return result


def _safe_pdb(value: Any) -> dict[str, Any]:
    result = _safe_resource_metadata(value)
    spec = value.get("spec") if isinstance(value, dict) and isinstance(value.get("spec"), dict) else {}
    result["spec"] = {"minAvailable": spec.get("minAvailable"), "maxUnavailable": spec.get("maxUnavailable"), "selector": deepcopy(spec.get("selector") or {})}
    return result


def _safe_named_resources(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_safe_resource_metadata(item) for item in values if isinstance(item, dict) and _safe_resource_metadata(item).get("name")]


def _selector_contains(container: Any, required: Any) -> bool:
    container = container if isinstance(container, dict) else {}
    required = required if isinstance(required, dict) else {}
    return bool(required) and all(str(container.get(key)) == str(value) for key, value in required.items())


def _disposable_target_config(profile: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    labels = ((workload.get("metadata") or {}).get("labels") or {}) if isinstance(workload, dict) else {}
    runtime = profile.get("extension_runtime") if isinstance(profile.get("extension_runtime"), dict) else {}
    for target in runtime.get("disposable_targets") or []:
        if not isinstance(target, dict):
            continue
        selector = target.get("selector") if isinstance(target.get("selector"), dict) else {}
        if _selector_contains(labels, selector):
            return deepcopy(target)
    return {}


def _safe_service(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    spec = source.get("spec") if isinstance(source.get("spec"), dict) else {}
    ports = []
    for port in spec.get("ports") or []:
        if isinstance(port, dict):
            ports.append({key: port.get(key) for key in ("name", "port", "targetPort", "protocol") if key in port})
    return {
        "metadata": _metadata(source.get("metadata")),
        "spec": {
            "selector": {str(key): str(item) for key, item in (spec.get("selector") or {}).items()},
            "ports": ports,
        },
    }


def _safe_pod(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    status = source.get("status") if isinstance(source.get("status"), dict) else {}
    return {
        "metadata": _metadata(source.get("metadata")) | {"uid": str((source.get("metadata") or {}).get("uid") or "")},
        "status": {
            "phase": status.get("phase"),
            "conditions": deepcopy(status.get("conditions") or []),
            "containerStatuses": [
                {key: item.get(key) for key in ("name", "ready", "restartCount", "state") if key in item}
                for item in (status.get("containerStatuses") or []) if isinstance(item, dict)
            ],
        },
    }


def _safe_ingress(value: Any) -> dict[str, Any]:
    """Keep only auditable ingress routing facts needed for dependency edges."""
    source = value if isinstance(value, dict) else {}
    spec = source.get("spec") if isinstance(source.get("spec"), dict) else {}
    backend_services: set[str] = set()

    def add_backend(backend: Any) -> None:
        if not isinstance(backend, dict):
            return
        service = backend.get("service")
        if isinstance(service, dict) and str(service.get("name") or "").strip():
            backend_services.add(str(service["name"]).strip())
        legacy_name = str(backend.get("serviceName") or "").strip()
        if legacy_name:
            backend_services.add(legacy_name)

    add_backend(spec.get("defaultBackend"))
    for rule in spec.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        http = rule.get("http") if isinstance(rule.get("http"), dict) else {}
        for path in http.get("paths") or []:
            if isinstance(path, dict):
                add_backend(path.get("backend"))
    return {
        "metadata": _metadata(source.get("metadata")),
        "spec": {
            "ingress_class_name": str(spec.get("ingressClassName") or ""),
            "backend_services": sorted(backend_services),
        },
    }


def _dependency_edges(
    services: list[dict[str, Any]],
    deployments: list[dict[str, Any]],
    ingresses: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Derive deterministic, non-mutating dependency edges from live facts."""
    edges: set[tuple[str, str, str, str, str, str]] = set()
    for service in services:
        service_metadata = service.get("metadata") if isinstance(service.get("metadata"), dict) else {}
        service_name = str(service_metadata.get("name") or "").strip()
        selector = (service.get("spec") or {}).get("selector") if isinstance(service.get("spec"), dict) else {}
        if not service_name or not isinstance(selector, dict) or not selector:
            continue
        for deployment in deployments:
            deployment_metadata = deployment.get("metadata") if isinstance(deployment.get("metadata"), dict) else {}
            deployment_name = str(deployment_metadata.get("name") or "").strip()
            deployment_spec = deployment.get("spec") if isinstance(deployment.get("spec"), dict) else {}
            deployment_selector = deployment_spec.get("selector") if isinstance(deployment_spec.get("selector"), dict) else {}
            match_labels = deployment_selector.get("matchLabels") if isinstance(deployment_selector, dict) else {}
            if service_name and deployment_name and _selector_contains(match_labels, selector):
                edges.add((service_name, deployment_name, "selects", "service", "deployment", f"service/{service_name}"))
    for ingress in ingresses:
        metadata = ingress.get("metadata") if isinstance(ingress.get("metadata"), dict) else {}
        ingress_name = str(metadata.get("name") or "").strip()
        spec = ingress.get("spec") if isinstance(ingress.get("spec"), dict) else {}
        for service_name in spec.get("backend_services") or []:
            service_name = str(service_name or "").strip()
            if ingress_name and service_name:
                edges.add((ingress_name, service_name, "routes_to", "ingress", "service", f"ingress/{ingress_name}"))
    return [
        {
            "source": source,
            "target": target,
            "relation": relation,
            "source_kind": source_kind,
            "target_kind": target_kind,
            "evidence": evidence,
        }
        for source, target, relation, source_kind, target_kind, evidence in sorted(edges)
    ]


class KubernetesProjectAdapter:
    """Build project facts from one namespace using read-only Kubernetes calls."""

    def __init__(self, *, profile: dict[str, Any], runner: Runner | None = None, kube_context: str | None = None) -> None:
        self.profile = deepcopy(profile)
        self.runner = runner or _default_runner
        self.kube_context = str(kube_context).strip() if kube_context else None
        if self.kube_context and not re.fullmatch(r"[A-Za-z0-9_.:@/-]+", self.kube_context):
            raise ValueError("kube_context contains unsafe characters")

    def _command(self, command: list[str]) -> list[str]:
        return ["--context", self.kube_context, *command] if self.kube_context else list(command)

    def _namespace(self) -> str:
        values = ((self.profile.get("namespace_policy") or {}).get("allowed_namespaces") or [])
        if len(values) != 1 or not str(values[0]).strip():
            raise ValueError("live inventory requires exactly one allowed namespace")
        return str(values[0]).strip()

    def _fault_families(self) -> tuple[str, ...]:
        """Use the profile matrix when declared, preserving legacy defaults."""
        if self.profile.get("runtime_contract") is None and self.profile.get("fault_support") is None:
            return FAULT_FAMILIES
        matrix = build_fault_matrix(self.profile)
        return tuple(item["fault_id"] for item in matrix["faults"] if item["status"] == "supported")

    def _get(self, resource: str, namespace: str) -> tuple[dict[str, Any] | None, str | None]:
        try:
            code, stdout, stderr = self.runner(self._command(["get", resource, "-n", namespace, "-o", "json"]), timeout=30)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            return None, f"{resource} probe failed: {type(exc).__name__}: {exc}"
        if code != 0:
            return None, (stderr or stdout).strip() or f"kubectl exit {code}"
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return None, f"invalid kubectl JSON for {resource}: {exc}"
        if not isinstance(value, dict):
            return None, f"kubectl {resource} response is not an object"
        return value, None

    def inventory(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            namespace = self._namespace()
        except ValueError as exc:
            return {
                "schema_version": "chaosatlas-live-inventory-v1",
                "status": "environment_blocked",
                "errors": [str(exc)],
                "warnings": [],
                "deployments": [],
                "services": [],
                "pods": [],
                "ingresses": [],
                "statefulsets": [],
                "daemonsets": [],
                "persistentvolumeclaims": [],
                "configmaps": [],
                "secrets": [],
                "horizontalpodautoscalers": [],
                "poddisruptionbudgets": [],
                "jobs": [],
                "workloads": [],
                "dependencies": [],
                "business_oracles": deepcopy([item for item in self.profile.get("business_oracles") or [] if isinstance(item, dict)]),
            }
        resources: dict[str, list[dict[str, Any]]] = {}
        errors: list[str] = []
        warnings: list[str] = []
        optional_resources = {"ingresses", "statefulsets", "daemonsets", "persistentvolumeclaims", "configmaps", "secrets", "horizontalpodautoscalers", "poddisruptionbudgets", "jobs"}
        for resource in ("deployments", "statefulsets", "daemonsets", "services", "pods", "ingresses", "persistentvolumeclaims", "configmaps", "secrets", "horizontalpodautoscalers", "poddisruptionbudgets", "jobs"):
            value, error = self._get(resource, namespace)
            if error:
                if resource in optional_resources:
                    warnings.append(f"{resource} unavailable: {error}")
                else:
                    errors.append(f"{resource} unavailable: {error}")
                resources[resource] = []
            else:
                resources[resource] = [item for item in (value or {}).get("items") or [] if isinstance(item, dict)]
        safe_deployments = [_safe_deployment(item) for item in resources["deployments"]]
        safe_statefulsets = [_safe_workload(item, "StatefulSet") for item in resources["statefulsets"]]
        safe_daemonsets = [_safe_workload(item, "DaemonSet") for item in resources["daemonsets"]]
        workloads = safe_deployments + safe_statefulsets + safe_daemonsets
        safe_services = [_safe_service(item) for item in resources["services"]]
        safe_pods = [_safe_pod(item) for item in resources["pods"]]
        safe_ingresses = [_safe_ingress(item) for item in resources["ingresses"]]
        dependencies = _dependency_edges(safe_services, workloads, safe_ingresses)
        dependencies.extend(
            normalize_declared_dependency_edges(
                self.profile.get("dependency_edges"),
                safe_services,
            )
        )
        dependencies = sorted(
            {json.dumps(item, sort_keys=True, ensure_ascii=True): item for item in dependencies}.values(),
            key=lambda item: (
                str(item.get("source") or ""),
                str(item.get("target") or ""),
                str(item.get("relation") or ""),
                str(item.get("id") or ""),
            ),
        )
        return {
            "schema_version": "chaosatlas-live-inventory-v1",
            "status": "environment_blocked" if errors else "verified",
            "checked_at": checked_at,
            "project_id": self.profile.get("project_id"),
            "project_commit": _commit(self.profile.get("project_commit")),
            "namespace": namespace,
            "deployments": safe_deployments,
            "statefulsets": safe_statefulsets,
            "daemonsets": safe_daemonsets,
            "workloads": workloads,
            "services": safe_services,
            "pods": safe_pods,
            "ingresses": safe_ingresses,
            "persistentvolumeclaims": [_safe_persistent_volume_claim(item) for item in resources["persistentvolumeclaims"]],
            "configmaps": _safe_named_resources(resources["configmaps"]),
            "secrets": _safe_named_resources(resources["secrets"]),
            "horizontalpodautoscalers": [_safe_hpa(item) for item in resources["horizontalpodautoscalers"]],
            "poddisruptionbudgets": [_safe_pdb(item) for item in resources["poddisruptionbudgets"]],
            "jobs": _safe_named_resources(resources["jobs"]),
            "dependencies": dependencies,
            "business_oracles": deepcopy([item for item in self.profile.get("business_oracles") or [] if isinstance(item, dict)]),
            "inventory_sha256": _hash({"workloads": workloads, "services": safe_services, "pods": safe_pods, "ingresses": safe_ingresses, "persistentvolumeclaims": resources["persistentvolumeclaims"], "configmaps": resources["configmaps"], "secrets": resources["secrets"], "horizontalpodautoscalers": resources["horizontalpodautoscalers"], "poddisruptionbudgets": resources["poddisruptionbudgets"], "jobs": resources["jobs"], "dependencies": dependencies}),
            "errors": errors,
            "warnings": warnings,
            "read_only": True,
        }

    def detect_server_deployment(self, inventory: dict[str, Any]) -> dict[str, Any]:
        if inventory.get("status") != "verified":
            return {"schema_version": "chaosatlas-server-deployment-detection-v1", "status": "environment_blocked", "errors": list(inventory.get("errors") or ["inventory is unavailable"]), "deployment_nodes": [], "candidates": []}
        namespace = str(inventory.get("namespace") or "")
        nodes: list[dict[str, Any]] = []
        errors: list[str] = []
        services = inventory.get("services") or []
        hpas = inventory.get("horizontalpodautoscalers") or []
        pdbs = inventory.get("poddisruptionbudgets") or []
        workloads = inventory.get("workloads") or inventory.get("deployments") or []
        for deployment in workloads:
            metadata = deployment.get("metadata") or {}
            name = str(metadata.get("name") or "")
            selector = ((deployment.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
            service = next((item for item in services if _selector_contains(selector, (item.get("spec") or {}).get("selector"))), None)
            enriched = deepcopy(deployment)
            extension_facts = enriched.get("extensions") if isinstance(enriched.get("extensions"), dict) else {}
            extension_capabilities = extension_facts.get("capabilities") if isinstance(extension_facts.get("capabilities"), dict) else {}
            extension_capabilities = deepcopy(extension_capabilities)
            extension_capabilities.setdefault(
                "networkchaos",
                bool({"network_delay", "network_loss", "network_partition"} & set(self._fault_families())),
            )
            disposable_target = _disposable_target_config(self.profile, deployment)
            if disposable_target:
                declared_capabilities = disposable_target.get("capabilities") if isinstance(disposable_target.get("capabilities"), dict) else {}
                extension_capabilities.update({str(key): bool(value) for key, value in declared_capabilities.items()})
            extension_facts["capabilities"] = extension_capabilities
            workload_kind = str(deployment.get("workload_kind") or "Deployment")
            matching_hpa = next((item for item in hpas if str((((item.get("spec") or {}).get("scaleTargetRef") or {}).get("name")) or "") == name), None)
            matching_pdb = next((item for item in pdbs if _selector_contains(selector, (((item.get("spec") or {}).get("selector") or {}).get("matchLabels")))), None)
            pod_spec = ((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}
            pvc_claims = [str(((volume.get("persistentVolumeClaim") or {}).get("claimName")) or "") for volume in pod_spec.get("volumes") or [] if isinstance(volume, dict) and isinstance(volume.get("persistentVolumeClaim"), dict)]
            pvc_claims.extend(str((item.get("metadata") or {}).get("name") or "") for item in (deployment.get("spec") or {}).get("volumeClaimTemplates") or [] if isinstance(item, dict))
            extension_facts["resource_facts"] = {
                "workload_kind": workload_kind,
                "hpa": deepcopy(matching_hpa),
                "pdb": deepcopy(matching_pdb),
                "pvc_claims": sorted({item for item in pvc_claims if item}),
                "configmap_count": len(inventory.get("configmaps") or []),
                "secret_count": len(inventory.get("secrets") or []),
                "disposable_target": bool(disposable_target),
                "disposable_target_id": str(disposable_target.get("id") or "") if disposable_target else "",
            }
            if disposable_target:
                extension_facts["writable_paths"] = sorted({str(item) for item in (disposable_target.get("io_test_paths") or []) if str(item).strip()})
            enriched["extensions"] = extension_facts
            enriched["availability_profile"] = {
                "manifest_facts_status": "verified",
                "pdb": deepcopy(matching_pdb),
                "hpa": deepcopy(matching_hpa),
                "recovery_contract": {"replacement_identity_required": True, "ready_required": True, "business_probe_required": True, "cleanup_required": True},
            }
            node = build_deployment_node(
                project_id=str(inventory.get("project_id") or ""),
                project_commit=_commit(inventory.get("project_commit")),
                namespace=namespace,
                deployment=enriched,
                service=service,
                source_refs=[f"cluster/{str(deployment.get('workload_kind') or 'Deployment').lower()}/{name}"],
                manifest_sha256=_hash(deployment),
            )
            validation_errors = validate_deployment_node(node)
            if validation_errors:
                errors.extend(f"{name}: {item}" for item in validation_errors)
            else:
                nodes.append(node)
        candidates = []
        for node in nodes:
            deployment = node["deployment"]
            for family in self._fault_families():
                if family == "container_kill" and not deployment.get("containers"):
                    continue
                candidates.append({
                    "candidate_id": f"server:{node['node_id']}:{family}",
                    "node_id": node["node_id"],
                    "target": deployment["name"],
                    "service_target": str(((node.get("service") or {}).get("name")) or deployment["name"]),
                    "target_kind": str(deployment.get("workload_kind") or "Deployment").lower(),
                    "workload_kind": str(deployment.get("workload_kind") or "Deployment"),
                    "disposable_target": bool((node.get("extensions") or {}).get("resource_facts", {}).get("disposable_target")),
                    "disposable_target_id": str((node.get("extensions") or {}).get("resource_facts", {}).get("disposable_target_id") or ""),
                    "namespace": namespace,
                    "selector": deepcopy(deployment["selector"]),
                    "fault_family": family,
                    "desired_replicas": deployment.get("desired_replicas"),
                    "recovery_contract": contract_for_fault(
                        (node.get("availability_profile") or {}).get("recovery_contract") or {},
                        family,
                    ),
                    "compile_eligible": True,
                    "static_prior": "singleton_availability_risk" if deployment.get("desired_replicas") == 1 and not (node.get("availability_profile") or {}).get("pdb") else None,
                })
        candidates = expand_candidates(candidates, self.profile.get("candidate_generation"))
        extension_space = generate_extension_candidates(
            nodes,
            inventory.get("dependencies") or [],
            networkchaos_available=bool({"network_delay", "network_loss", "network_partition"} & set(self._fault_families())),
        )
        return {
            "schema_version": "chaosatlas-server-deployment-detection-v1",
            "status": "method_invalid" if errors else "verified",
            "project_id": inventory.get("project_id"),
            "namespace": namespace,
            "deployment_nodes": nodes,
            "candidates": candidates,
            "extension_candidates": extension_space["candidates"],
            "extension_capability_matrix": extension_space["matrix"],
            "errors": errors,
            "claim_scope": "runtime_inventory",
        }

    def map_test_nodes(self, detection: dict[str, Any]) -> dict[str, Any]:
        candidates = [deepcopy(item) for item in detection.get("candidates") or []]
        candidates.extend(deepcopy(item) for item in detection.get("extension_candidates") or [])
        return {
            "schema_version": "chaosatlas-candidate-space-v1",
            "status": "verified" if detection.get("status") == "verified" and candidates else "environment_blocked" if detection.get("status") == "environment_blocked" else "method_invalid",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "claim_scope": "runtime_inventory",
            "errors": list(detection.get("errors") or []),
        }
