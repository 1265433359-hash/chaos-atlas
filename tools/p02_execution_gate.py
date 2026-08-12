"""Read-only execution gate for P02 generated Chaos Mesh manifests.

This gate is deliberately separate from the older Train Ticket runner.  It
accepts only the P02 namespace, resolves selectors against live Pods, checks
the installed Chaos Mesh CRDs/controller Pods, and confirms that no resource
with the generated name already exists.  It never applies or deletes a
resource.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "chaosatlas-p02"
RESOURCE_BY_KIND = {
    "PodChaos": "podchaos",
    "NetworkChaos": "networkchaos",
    "StressChaos": "stresschaos",
}


def chaos_components(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only the controller and daemon Pods required for injection."""
    required = ("chaos-controller-manager", "chaos-daemon")
    return [
        item
        for item in items
        if any(str(item.get("metadata", {}).get("name", "")).startswith(prefix) for prefix in required)
    ]


def component_namespace(items: list[dict[str, Any]]) -> str | None:
    """Find one namespace containing both required Chaos Mesh components."""
    roles: dict[str, set[str]] = {}
    for item in chaos_components(items):
        metadata = item.get("metadata", {})
        namespace = str(metadata.get("namespace", ""))
        name = str(metadata.get("name", ""))
        if namespace:
            roles.setdefault(namespace, set()).add("controller" if name.startswith("chaos-controller-manager") else "daemon")
    matches = sorted(namespace for namespace, found in roles.items() if found == {"controller", "daemon"})
    return matches[0] if len(matches) == 1 else None


def kubectl(args: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        p = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, "", str(exc)


def json_get(args: list[str]) -> tuple[Any | None, str | None]:
    code, out, err = kubectl([*args, "-o", "json"])
    if code != 0:
        return None, (err or out).strip()
    try:
        return json.loads(out), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def ready(pod: dict[str, Any]) -> bool:
    return not pod.get("metadata", {}).get("deletionTimestamp") and any(
        c.get("type") == "Ready" and c.get("status") == "True"
        for c in pod.get("status", {}).get("conditions", [])
        if isinstance(c, dict)
    )


def check(path: Path, chaos_namespace: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # fail closed
        return {"mutation": str(path).replace("\\", "/"), "decision": "blocked", "errors": [str(exc)]}
    if not isinstance(document, dict):
        return {"mutation": str(path).replace("\\", "/"), "decision": "blocked", "errors": ["YAML root is not an object"]}
    kind = str(document.get("kind", ""))
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    selector = spec.get("selector") or {}
    labels = selector.get("labelSelectors") or {}
    namespaces = selector.get("namespaces") or []
    namespace = metadata.get("namespace")
    name = metadata.get("name")
    checks: dict[str, Any] = {}
    checks["namespace"] = namespace == NAMESPACE and namespaces == [NAMESPACE]
    checks["mode"] = spec.get("mode") == "one"
    checks["labels_nonempty"] = isinstance(labels, dict) and bool(labels)
    if not checks["namespace"]: errors.append("manifest must be scoped to chaosatlas-p02")
    if not checks["mode"]: errors.append("only mode=one is allowed")
    if not checks["labels_nonempty"]: errors.append("selector.labelSelectors must be non-empty")
    resource = RESOURCE_BY_KIND.get(kind)
    checks["kind"] = resource is not None
    if not resource: errors.append(f"unsupported Chaos Mesh kind: {kind}")

    if resource:
        code, out, err = kubectl(["get", "crd", f"{resource}.chaos-mesh.org"])
        checks["crd"] = code == 0
        if code != 0: errors.append((err or out).strip())
    pods, pod_error = json_get(["get", "pods", "-n", NAMESPACE, "-l", ",".join(f"{k}={v}" for k, v in sorted(labels.items()))]) if checks["labels_nonempty"] else (None, None)
    live_pods = (pods or {}).get("items", []) if isinstance(pods, dict) else []
    checks["target_pods"] = [{"name": p.get("metadata", {}).get("name"), "uid": p.get("metadata", {}).get("uid"), "ready": ready(p)} for p in live_pods]
    checks["target_pods_ready"] = bool(live_pods) and all(ready(p) for p in live_pods)
    if pod_error: errors.append(f"target pod lookup failed: {pod_error}")
    elif not live_pods: errors.append("selector matched no live Pods")
    elif not checks["target_pods_ready"]: errors.append("one or more target Pods are not Ready")

    if chaos_namespace:
        components, component_error = json_get(["get", "pods", "-n", chaos_namespace])
        all_component_pods = (components or {}).get("items", []) if isinstance(components, dict) else []
    else:
        components, component_error = json_get(["get", "pods", "-A"])
        all_component_pods = (components or {}).get("items", []) if isinstance(components, dict) else []
        chaos_namespace = component_namespace(all_component_pods)
        if not chaos_namespace and not component_error:
            component_error = "could not uniquely identify a namespace with Chaos Mesh controller and daemon Pods"
    chaos_pods = [
        pod for pod in chaos_components(all_component_pods)
        if pod.get("metadata", {}).get("namespace", chaos_namespace) == chaos_namespace
    ]
    component_names = {str(pod.get("metadata", {}).get("name", "")) for pod in chaos_pods}
    required_components_present = (
        any(name.startswith("chaos-controller-manager") for name in component_names)
        and any(name.startswith("chaos-daemon") for name in component_names)
    )
    checks["chaos_mesh_namespace"] = chaos_namespace
    checks["chaos_mesh_pods"] = [{"name": p.get("metadata", {}).get("name"), "ready": ready(p)} for p in chaos_pods]
    checks["chaos_mesh_ready"] = required_components_present and all(ready(p) for p in chaos_pods)
    if component_error: errors.append(f"Chaos Mesh lookup failed: {component_error}")
    elif not checks["chaos_mesh_ready"]: errors.append("Chaos Mesh Pods are not all Ready")

    if resource and name and namespace:
        code, out, err = kubectl(["get", resource, str(name), "-n", str(namespace)])
        checks["name_available"] = code != 0 and "not found" in (err or out).lower()
        if code == 0: errors.append("mutation resource already exists")
        elif not checks["name_available"]: errors.append(f"cannot confirm mutation name availability: {(err or out).strip()}")
    else:
        checks["name_available"] = False
    checks["baseline_evidence"] = (ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P02/baseline_gateway_valid_2026-08-12.json").exists()
    checks["recovery_evidence"] = (ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_profiles/P02/business_oracles_valid_2026-08-12.json").exists()
    if not checks["baseline_evidence"] or not checks["recovery_evidence"]:
        errors.append("P02 baseline/recovery evidence is incomplete")
    decision = "ready_for_injection" if not errors else "blocked"
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "mutation": str(path).replace("\\", "/"), "kind": kind, "namespace": namespace, "name": name, "checks": checks, "decision": decision, "errors": errors, "mutation_applied": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mutations", nargs="+", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--chaos-namespace", default=os.environ.get("CHAOS_MESH_NAMESPACE"))
    args = parser.parse_args()
    results = [check(path, args.chaos_namespace) for path in args.mutations]
    report = {"schema_version": "1.0", "tool": "p02_execution_gate", "mutation_applied": False, "results": results, "summary": {"ready_for_injection": sum(x["decision"] == "ready_for_injection" for x in results), "blocked": sum(x["decision"] == "blocked" for x in results)}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["summary"]["blocked"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
