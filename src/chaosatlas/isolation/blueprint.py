"""Compile Kubernetes isolation blueprints without copying sensitive state."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


ALLOWED_KINDS = {"ConfigMap", "Secret", "Service", "Deployment", "StatefulSet", "Job", "PersistentVolumeClaim"}
FORBIDDEN_POD_KEYS = {"hostNetwork", "hostPID", "hostIPC", "hostUsers"}
FORBIDDEN_REFERENCE_KEYS = {
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


def _validate_resource(resource: dict[str, Any], declared: dict[str, set[str]]) -> list[str]:
    errors: list[str] = []
    kind = str(resource.get("kind") or "")
    if kind not in ALLOWED_KINDS:
        errors.append(f"unsupported blueprint kind: {kind}")
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    if not metadata.get("name"):
        errors.append(f"{kind or 'resource'} name is required")
    if kind == "Secret" and (resource.get("data") or resource.get("stringData")):
        errors.append("blueprint Secret values are forbidden")
    if kind == "Secret":
        generated = resource.get("runtimeGenerate")
        if not isinstance(generated, dict) or not isinstance(generated.get("keys"), list) or not generated.get("keys"):
            errors.append("blueprint Secret must declare non-empty runtimeGenerate.keys")
        elif any(not isinstance(key, str) or not key or len(key) > 128 for key in generated["keys"]):
            errors.append("runtimeGenerate.keys contains an invalid key")
        templates = generated.get("templates") if isinstance(generated, dict) else None
        if templates is not None and (not isinstance(templates, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in templates.items())):
            errors.append("runtimeGenerate.templates must map keys to string templates")
        elif isinstance(templates, dict):
            generated_keys = set(generated.get("keys") or [])
            for key, template in templates.items():
                references = set(re.findall(r"\$\{([^{}]+)\}", template))
                if not key or len(key) > 128 or not references or not references.issubset(generated_keys):
                    errors.append("runtimeGenerate.templates must reference declared generated keys")
    if kind == "PersistentVolumeClaim":
        spec = resource.get("spec") if isinstance(resource.get("spec"), dict) else {}
        if any(spec.get(key) not in (None, "", {}, []) for key in ("dataSource", "dataSourceRef", "selector", "volumeName")):
            errors.append("PersistentVolumeClaim source binding is forbidden")
    for mapping in _walk(resource):
        if any(mapping.get(key) is not None and mapping.get(key) is not False for key in FORBIDDEN_POD_KEYS):
            errors.append("host namespace sharing is forbidden")
        if isinstance(mapping.get("hostPath"), dict):
            errors.append("hostPath is forbidden")
        for key in FORBIDDEN_REFERENCE_KEYS:
            if key in mapping and mapping.get(key) not in (None, False, "", [], {}):
                errors.append(f"{key} is forbidden")
        for key, expected_kind in (("secretKeyRef", "Secret"), ("configMapKeyRef", "ConfigMap")):
            reference = mapping.get(key)
            if isinstance(reference, dict) and str(reference.get("name") or "") not in declared[expected_kind]:
                errors.append(f"{key} must reference a resource created by this lease")
        env_from = mapping.get("envFrom")
        if isinstance(env_from, list):
            for source in env_from:
                source = source if isinstance(source, dict) else {}
                for key, expected_kind in (("secretRef", "Secret"), ("configMapRef", "ConfigMap")):
                    reference = source.get(key)
                    if isinstance(reference, dict) and str(reference.get("name") or "") not in declared[expected_kind]:
                        errors.append(f"envFrom {key} must reference a resource created by this lease")
        claim = mapping.get("persistentVolumeClaim")
        if isinstance(claim, dict) and str(claim.get("claimName") or "") not in declared["PersistentVolumeClaim"]:
            errors.append("persistentVolumeClaim must reference a resource created by this lease")
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
    declared = {kind: set() for kind in ("ConfigMap", "Secret", "PersistentVolumeClaim")}
    for item in resources:
        if isinstance(item, dict) and str(item.get("kind") or "") in declared:
            name = str(((item.get("metadata") or {}).get("name")) or "")
            if name:
                declared[str(item["kind"])].add(name)
    errors = [error for item in resources if isinstance(item, dict) for error in _validate_resource(item, declared)]
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
        if item.get("kind") in {"Deployment", "StatefulSet", "Job"}:
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
