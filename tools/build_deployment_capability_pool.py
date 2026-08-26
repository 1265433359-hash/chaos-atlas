"""Build a manifest-only deployment capability pool and local impact graph."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

try:
    from tools.deployment_capability import build_deployment_node, validate_deployment_node
    from tools.recovery_contract import contract_for_fault
except ModuleNotFoundError:  # direct script invocation
    from deployment_capability import build_deployment_node, validate_deployment_node
    from recovery_contract import contract_for_fault


FAULT_FAMILIES = ("pod_kill", "container_kill", "stress_cpu", "stress_memory", "network_loss", "network_partition")


def _documents(root: Path) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
    documents: list[tuple[Path, dict[str, Any]]] = []
    errors: list[str] = []
    for path in sorted([*root.rglob("*.yaml"), *root.rglob("*.yml")]):
        try:
            for item in yaml.safe_load_all(path.read_text(encoding="utf-8")):
                if isinstance(item, dict) and item.get("kind"):
                    documents.append((path, item))
        except (OSError, yaml.YAMLError, UnicodeError) as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    return documents, errors


def build_pool(root: Path, *, project_id: str, project_commit: str, namespace: str) -> dict[str, Any]:
    root = Path(root)
    if not root.exists() or not str(project_commit).strip():
        return {"schema_version": 1, "status": "static_blocked", "reason": "manifest root or project commit unavailable", "deployment_nodes": [], "impact_graph": [], "candidates": []}
    docs, errors = _documents(root)
    if errors:
        return {"schema_version": 1, "status": "static_blocked", "reason": "manifest parse failed", "errors": errors, "deployment_nodes": [], "impact_graph": [], "candidates": []}
    deployments = [(path, doc) for path, doc in docs if doc.get("kind") == "Deployment"]
    services = [doc for _, doc in docs if doc.get("kind") == "Service"]
    pdbs = [doc for _, doc in docs if doc.get("kind") == "PodDisruptionBudget"]
    hpas = [doc for _, doc in docs if doc.get("kind") == "HorizontalPodAutoscaler"]
    nodes: list[dict[str, Any]] = []
    graph: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    source_bytes = bytearray()
    for path in sorted([*root.rglob("*.yaml"), *root.rglob("*.yml")]):
        try: source_bytes.extend(path.read_bytes())
        except OSError: pass
    manifest_hash = hashlib.sha256(bytes(source_bytes)).hexdigest()
    for path, deployment in deployments:
        selector = ((deployment.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
        name = str((deployment.get("metadata") or {}).get("name") or "")
        matched_service = next((svc for svc in services if (svc.get("spec") or {}).get("selector") == selector), None)
        profile = {
            "manifest_facts_status": "verified",
            "pdb": None,
            "hpa": None,
            "recovery_contract": {
                "replacement_identity_required": True,
                "ready_required": True,
                "business_probe_required": True,
                "cleanup_required": True,
            },
        }
        for item in pdbs:
            if (item.get("spec") or {}).get("selector", {}).get("matchLabels") == selector:
                profile["pdb"] = {"name": (item.get("metadata") or {}).get("name"), "min_available": (item.get("spec") or {}).get("minAvailable"), "max_unavailable": (item.get("spec") or {}).get("maxUnavailable")}
        for item in hpas:
            target = (item.get("spec") or {}).get("scaleTargetRef") or {}
            if target.get("name") == name:
                profile["hpa"] = {"name": (item.get("metadata") or {}).get("name"), "min_replicas": (item.get("spec") or {}).get("minReplicas"), "max_replicas": (item.get("spec") or {}).get("maxReplicas")}
        enriched = dict(deployment)
        enriched["availability_profile"] = profile
        relative = path.relative_to(root).as_posix()
        node = build_deployment_node(project_id=project_id, project_commit=project_commit, namespace=namespace, deployment=enriched, service=matched_service, source_refs=[relative], manifest_sha256=manifest_hash)
        validation_errors = validate_deployment_node(node)
        if validation_errors:
            return {"schema_version": 1, "status": "static_blocked", "reason": "deployment node invalid", "errors": validation_errors, "deployment_nodes": [], "impact_graph": [], "candidates": []}
        nodes.append(node)
        dep_id = node["node_id"]
        pod_id = f"pod:{dep_id}"
        rs_id = f"replicaset:{dep_id}"
        graph.extend([
            {"source": dep_id, "target": rs_id, "relation": "deployment_replicaset"},
            {"source": rs_id, "target": pod_id, "relation": "replicaset_pod"},
            {"source": f"probe:{dep_id}", "target": pod_id, "relation": "probe_readiness"},
            {"source": f"recovery:{dep_id}", "target": f"business_probe:{dep_id}", "relation": "replacement_pod_business_probe"},
        ])
        if matched_service:
            graph.append({"source": f"service:{(matched_service.get('metadata') or {}).get('name')}", "target": pod_id, "relation": "service_selector"})
        eligible = bool((node["deployment"].get("selector") or {})) and node["availability_profile"].get("manifest_facts_status") == "verified"
        candidates.append({
            "target": dep_id,
            "target_kind": "deployment",
            "deployment": name,
            "fault_families": list(FAULT_FAMILIES),
            "recovery_contracts": {
                family: contract_for_fault(node["availability_profile"].get("recovery_contract"), family)
                for family in FAULT_FAMILIES
            },
            "compile_eligible": eligible,
            "static_prior": "availability_static_prior" if node["deployment"].get("desired_replicas") == 1 and not node["availability_profile"].get("pdb") else None,
        })
    return {"schema_version": 1, "status": "verified", "project_id": project_id, "project_commit": project_commit, "namespace": namespace, "deployment_nodes": nodes, "impact_graph": graph, "candidates": candidates, "manifest_sha256": manifest_hash}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--project-commit", default="")
    parser.add_argument("--namespace", default="chaosatlas-sock-shop")
    parser.add_argument("--manifest-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_pool(args.manifest_root, project_id=args.project, project_commit=args.project_commit, namespace=args.namespace)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "deployment_capability_pool.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "nodes": len(result["deployment_nodes"]), "output": str(args.output)}, ensure_ascii=True))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
