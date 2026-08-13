"""Read-only P09 execution gate for the unified ChaosAtlas lifecycle."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "chaosatlas-p09"
RESOURCE_BY_KIND = {
    "PodChaos": "podchaos",
    "NetworkChaos": "networkchaos",
    "StressChaos": "stresschaos",
}
DEFAULT_PROFILE_GATE = (
    ROOT
    / "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P09-r4/profile-preflight.json"
)


def kubectl(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["kubectl", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, "", str(exc)


def kubectl_json(args: list[str]) -> tuple[Any | None, str | None]:
    code, out, err = kubectl([*args, "-o", "json"])
    if code != 0:
        return None, (err or out).strip()
    try:
        return json.loads(out), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def ready(pod: dict[str, Any]) -> bool:
    return not pod.get("metadata", {}).get("deletionTimestamp") and any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in pod.get("status", {}).get("conditions", [])
        if isinstance(condition, dict)
    )


def check(
    mutation_path: Path,
    *,
    profile_gate: Path = DEFAULT_PROFILE_GATE,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        document = yaml.safe_load(mutation_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "decision": "blocked",
            "mutation": str(mutation_path).replace("\\", "/"),
            "errors": [str(exc)],
        }
    if not isinstance(document, dict):
        return {
            "decision": "blocked",
            "mutation": str(mutation_path).replace("\\", "/"),
            "errors": ["YAML root is not an object"],
        }

    kind = str(document.get("kind") or "")
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    selector = spec.get("selector") or {}
    labels = selector.get("labelSelectors") or {}
    namespaces = selector.get("namespaces") or []
    name = str(metadata.get("name") or "")
    resource = RESOURCE_BY_KIND.get(kind)
    checks: dict[str, Any] = {}

    try:
        gate = json.loads(profile_gate.read_text(encoding="utf-8"))
        gate_allowed = gate.get("apply_allowed") is True or gate.get(
            "runtime_apply_allowed"
        ) is True
    except Exception as exc:
        gate = {"error": str(exc)}
        gate_allowed = False
    checks["profile_gate"] = {
        "path": str(profile_gate).replace("\\", "/"),
        "allowed": gate_allowed,
        "record": gate,
    }
    if not gate_allowed:
        errors.append("P09 profile gate does not allow runtime apply")

    checks["namespace"] = metadata.get("namespace") == NAMESPACE and namespaces == [
        NAMESPACE
    ]
    if not checks["namespace"]:
        errors.append("manifest must be scoped to chaosatlas-p09")
    checks["mode"] = spec.get("mode") == "one"
    if not checks["mode"]:
        errors.append("only mode=one is allowed")
    checks["kind"] = resource is not None
    if not resource:
        errors.append(f"unsupported Chaos Mesh kind: {kind}")
    checks["selector_nonempty"] = isinstance(labels, dict) and bool(labels)
    if not checks["selector_nonempty"]:
        errors.append("selector.labelSelectors must be non-empty")

    if resource:
        code, out, err = kubectl(["get", "crd", f"{resource}.chaos-mesh.org"])
        checks["crd"] = code == 0
        if code != 0:
            errors.append((err or out).strip())

    if checks["selector_nonempty"] and checks["namespace"]:
        selector_text = ",".join(
            f"{key}={value}" for key, value in sorted(labels.items())
        )
        pods, pod_error = kubectl_json(
            ["get", "pods", "-n", NAMESPACE, "-l", selector_text]
        )
        live_pods = (pods or {}).get("items", []) if isinstance(pods, dict) else []
        checks["target_pods"] = [
            {
                "name": pod.get("metadata", {}).get("name"),
                "uid": pod.get("metadata", {}).get("uid"),
                "ready": ready(pod),
            }
            for pod in live_pods
        ]
        checks["target_pods_ready"] = bool(live_pods) and all(
            ready(pod) for pod in live_pods
        )
        if pod_error:
            errors.append(f"target pod lookup failed: {pod_error}")
        elif not live_pods:
            errors.append("selector matched no live Pods")
        elif not checks["target_pods_ready"]:
            errors.append("one or more target Pods are not Ready")

    if resource and name and metadata.get("namespace") == NAMESPACE:
        code, out, err = kubectl(["get", resource, name, "-n", NAMESPACE])
        checks["name_available"] = code != 0 and "not found" in (err or out).lower()
        if code == 0:
            errors.append("mutation resource already exists")
        elif not checks["name_available"]:
            errors.append(
                f"cannot confirm mutation name availability: {(err or out).strip()}"
            )
    else:
        checks["name_available"] = False

    return {
        "schema_version": "p09-execution-gate-v1",
        "project_id": "P09",
        "namespace": NAMESPACE,
        "mutation": str(mutation_path).replace("\\", "/"),
        "kind": kind,
        "name": name,
        "checks": checks,
        "decision": "ready_for_injection" if not errors else "blocked",
        "errors": errors,
        "mutation_applied": False,
    }
