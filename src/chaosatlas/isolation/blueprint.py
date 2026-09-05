"""Compile Kubernetes isolation blueprints without copying sensitive state."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ALLOWED_KINDS = {"ConfigMap", "Secret", "Service", "Deployment", "StatefulSet", "NetworkPolicy", "ResourceQuota", "LimitRange"}
FORBIDDEN_POD_KEYS = {"hostNetwork", "hostPID", "hostIPC", "hostUsers"}
FORBIDDEN_REFERENCE_KEYS = {
    "envFrom",
    "secretKeyRef",
    "configMapKeyRef",
    "persistentVolumeClaim",
    "imagePullSecrets",
    "serviceAccount",
    "serviceAccountName",
    "hostAliases",
    "nodeName",
}


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _validate_resource(resource: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    kind = str(resource.get("kind") or "")
    if kind not in ALLOWED_KINDS:
        errors.append(f"unsupported blueprint kind: {kind}")
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    if not metadata.get("name"):
        errors.append(f"{kind or 'resource'} name is required")
    if kind == "Secret" and (resource.get("data") or resource.get("stringData")):
        errors.append("blueprint Secret values are forbidden")
    for mapping in _walk(resource):
        if any(mapping.get(key) is not None and mapping.get(key) is not False for key in FORBIDDEN_POD_KEYS):
            errors.append("host namespace sharing is forbidden")
        if isinstance(mapping.get("hostPath"), dict):
            errors.append("hostPath is forbidden")
        for key in FORBIDDEN_REFERENCE_KEYS:
            if key in mapping and mapping.get(key) not in (None, False, "", [], {}):
                errors.append(f"{key} is forbidden")
        if mapping.get("hostPort") not in (None, 0, ""):
            errors.append("hostPort is forbidden")
        security = mapping.get("securityContext") if isinstance(mapping.get("securityContext"), dict) else {}
        if security.get("privileged") is True:
            errors.append("privileged containers are forbidden")
        capabilities = security.get("capabilities") if isinstance(security.get("capabilities"), dict) else {}
        if capabilities.get("add"):
            errors.append("added Linux capabilities are forbidden")
    return sorted(set(errors))


def compile_blueprint(
    blueprint: dict[str, Any],
    *,
    namespace: str,
    owner_labels: dict[str, str],
) -> list[dict[str, Any]]:
    resources = blueprint.get("resources") if isinstance(blueprint.get("resources"), list) else []
    if not resources:
        raise ValueError("blueprint resources are required")
    errors = [error for item in resources if isinstance(item, dict) for error in _validate_resource(item)]
    if len(resources) != sum(isinstance(item, dict) for item in resources):
        errors.append("every blueprint resource must be an object")
    if errors:
        raise ValueError("unsafe isolation blueprint: " + "; ".join(sorted(set(errors))))
    compiled: list[dict[str, Any]] = []
    for source in resources:
        item = deepcopy(source)
        item.pop("status", None)
        metadata = item.setdefault("metadata", {})
        for key in ("uid", "resourceVersion", "generation", "creationTimestamp", "managedFields", "ownerReferences"):
            metadata.pop(key, None)
        metadata["namespace"] = namespace
        metadata["labels"] = {**{str(k): str(v) for k, v in (metadata.get("labels") or {}).items()}, **owner_labels}
        if item.get("kind") in {"Deployment", "StatefulSet"}:
            template_metadata = item.setdefault("spec", {}).setdefault("template", {}).setdefault("metadata", {})
            template_metadata["labels"] = {
                **{str(k): str(v) for k, v in (template_metadata.get("labels") or {}).items()},
                **owner_labels,
            }
            pod_spec = item["spec"]["template"].setdefault("spec", {})
            pod_spec["automountServiceAccountToken"] = False
        if item.get("kind") == "Secret":
            item["type"] = "Opaque"
            item.pop("data", None)
            item.pop("stringData", None)
        compiled.append(item)
    return compiled


def derive_l2_blueprint(target: dict[str, Any], project_id: str) -> dict[str, Any]:
    extensions = target.get("extensions") if isinstance(target.get("extensions"), dict) else {}
    containers = extensions.get("container_blueprints") if isinstance(extensions.get("container_blueprints"), list) else []
    safe_containers = []
    for index, source in enumerate(containers):
        if not isinstance(source, dict) or not str(source.get("image") or ""):
            continue
        container = {
            "name": str(source.get("name") or f"target-{index}"),
            "image": str(source["image"]),
            "resources": deepcopy(source.get("resources") or {"requests": {"cpu": "10m", "memory": "16Mi"}, "limits": {"cpu": "250m", "memory": "256Mi"}}),
        }
        if source.get("ports"):
            container["ports"] = deepcopy(source["ports"])
        if index == 0:
            container["volumeMounts"] = [{"name": "chaosatlas-test", "mountPath": "/chaosatlas-test"}]
        safe_containers.append(container)
    if not safe_containers:
        raise ValueError("target has no safe container image facts")
    labels = {"app.kubernetes.io/name": f"ca-{project_id[:30]}-sandbox"}
    return {
        "resources": [{
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "sandbox-target"},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": labels},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {"automountServiceAccountToken": False, "containers": safe_containers, "volumes": [{"name": "chaosatlas-test", "emptyDir": {}}]},
                },
            },
        }],
    }
