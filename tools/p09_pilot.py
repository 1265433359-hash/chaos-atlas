"""Compile the frozen P09 API PodKill candidate into a bounded pilot mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


NAMESPACE = "chaosatlas-p09"
CANDIDATE_ID = "P09-api-pod_kill-01"
TARGET_NODE = "compose/service/api"
API_SELECTOR = {
    "app.kubernetes.io/name": "api",
    "app.kubernetes.io/part-of": NAMESPACE,
}


class PilotCompileError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _api_deployment(profile_path: Path) -> dict[str, Any]:
    documents = list(yaml.safe_load_all(profile_path.read_text(encoding="utf-8")))
    matches = [
        doc
        for doc in documents
        if isinstance(doc, dict)
        and doc.get("kind") == "Deployment"
        and doc.get("metadata", {}).get("name") == "api"
    ]
    if len(matches) != 1:
        raise PilotCompileError("profile must contain exactly one API Deployment")
    deployment = matches[0]
    if deployment.get("metadata", {}).get("namespace") != NAMESPACE:
        raise PilotCompileError("API Deployment must be namespace-local to chaosatlas-p09")
    labels = deployment.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
    if any(labels.get(key) != value for key, value in API_SELECTOR.items()):
        raise PilotCompileError("API Deployment does not expose the exact pilot selector")
    return deployment


def compile_api_pod_kill(
    candidate: dict[str, Any], topology: dict[str, Any], profile_path: Path
) -> dict[str, Any]:
    expected = {
        "candidate_id": CANDIDATE_ID,
        "project_id": "P09",
        "target": "api",
        "fault_family": "pod_kill",
        "workload_id": "P09-primary-workload",
    }
    if any(candidate.get(key) != value for key, value in expected.items()):
        raise PilotCompileError("only the frozen P09 API PodKill candidate is accepted")
    if candidate.get("fault_parameters") != {"duration_s": 0, "mode": "one"}:
        raise PilotCompileError("frozen PodKill parameters differ from the registered candidate")
    nodes = [node for node in topology.get("nodes", []) if node.get("id") == TARGET_NODE]
    if not nodes:
        raise PilotCompileError("P09 topology does not contain compose/service/api")
    _api_deployment(profile_path)

    profile_bytes = profile_path.read_bytes()
    candidate_bytes = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity = sha256_bytes(candidate_bytes + sha256_bytes(profile_bytes).encode("ascii"))
    name = f"p09-api-pod-kill-{identity[:12]}"
    mutation = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {
            "name": name,
            "namespace": NAMESPACE,
            "labels": {
                "chaosatlas.dev/project": "p09",
                "chaosatlas.dev/purpose": "bounded-pilot",
            },
        },
        "spec": {
            "action": "pod-kill",
            "mode": "one",
            "selector": {
                "namespaces": [NAMESPACE],
                "labelSelectors": API_SELECTOR,
            },
            "duration": "30s",
        },
    }
    yaml_text = yaml.safe_dump(mutation, sort_keys=False)
    provenance = {
        "schema_version": "1.0",
        "project_id": "P09",
        "candidate_id": CANDIDATE_ID,
        "candidate_sha256": sha256_bytes(candidate_bytes),
        "support_status_before_pilot": candidate.get("support_status"),
        "topology_graph_hash": topology.get("graph_hash"),
        "runtime_mapping": {
            "source_node": TARGET_NODE,
            "namespace": NAMESPACE,
            "workload": {"kind": "Deployment", "name": "api"},
            "selector": API_SELECTOR,
        },
        "profile_path": str(profile_path).replace("\\", "/"),
        "profile_sha256": sha256_bytes(profile_bytes),
        "mutation_sha256": sha256_bytes(yaml_text.encode("utf-8")),
        "execution_ready": False,
        "human_review": "pending",
    }
    return {"yaml": yaml_text, "provenance": provenance}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-pool", type=Path, required=True)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    pool = json.loads(args.candidate_pool.read_text(encoding="utf-8-sig"))
    candidates = [item for item in pool.get("candidates", []) if item.get("candidate_id") == CANDIDATE_ID]
    if len(candidates) != 1:
        raise SystemExit("frozen candidate pool must contain exactly one P09 API PodKill candidate")
    topology = json.loads(args.topology.read_text(encoding="utf-8-sig"))
    result = compile_api_pod_kill(candidates[0], topology, args.profile)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(f"refusing to overwrite nonempty output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    mutation_path = args.output_dir / "p09-api-pod-kill.yaml"
    provenance_path = args.output_dir / "p09-api-pod-kill.provenance.json"
    mutation_path.write_bytes(result["yaml"].encode("utf-8"))
    provenance = dict(result["provenance"])
    provenance["mutation_path"] = str(mutation_path).replace("\\", "/")
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "status": "compiled_requires_runtime_gate",
        "candidate_id": CANDIDATE_ID,
        "mutation_path": str(mutation_path).replace("\\", "/"),
        "provenance_path": str(provenance_path).replace("\\", "/"),
        "mutation_sha256": provenance["mutation_sha256"],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
