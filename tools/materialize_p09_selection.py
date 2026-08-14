"""Materialize P09 fixed-pool selections into auditable Chaos Mesh mutations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "chaosatlas-p09"
DEFAULT_SELECTION_ROOT = ROOT / "artifacts/experiments/chaosatlas_10_projects/selection_results/P09/teacher-minikube-dual-r1"
DEFAULT_POOL = ROOT / "artifacts/experiments/chaosatlas_10_projects/candidate_pools/P09/candidate_pool.json"
DEFAULT_OUTPUT = ROOT / "artifacts/experiments/chaosatlas_10_projects/runtime_results/P09/teacher-minikube-selection-unified-r1"
TARGET_LABELS = {
    "app.kubernetes.io/name": "{target}",
    "app.kubernetes.io/part-of": NAMESPACE,
    "chaosatlas.io/profile": "minimal",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")


def yaml_for(candidate: dict[str, Any], resource_name: str) -> str:
    family = candidate["fault_family"]
    params = candidate.get("fault_parameters") or {}
    selector = {
        "namespaces": [NAMESPACE],
        "labelSelectors": {
            key: value.format(target=candidate["target"])
            for key, value in TARGET_LABELS.items()
        },
    }
    metadata = {
        "name": resource_name,
        "namespace": NAMESPACE,
        "labels": {
            "chaosatlas.dev/project": "p09",
            "chaosatlas.dev/generator": "selection_materializer_v1",
            "chaosatlas.dev/candidate": candidate["candidate_id"],
        },
    }
    document: dict[str, Any] = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "metadata": metadata,
        "spec": {"mode": "one", "selector": selector},
    }
    if family == "pod_kill":
        document["kind"] = "PodChaos"
        document["spec"].update({"action": "pod-kill", "duration": "30s"})
    elif family == "network_delay":
        document["kind"] = "NetworkChaos"
        document["spec"].update({
            "action": "delay",
            "delay": {
                "latency": f"{int(params['latency_ms'])}ms",
                "correlation": "100",
                "jitter": "0ms",
            },
            "duration": f"{int(params['duration_s'])}s",
            "direction": "to",
        })
    elif family == "network_loss":
        document["kind"] = "NetworkChaos"
        document["spec"].update({
            "action": "loss",
            "loss": {"loss": str(params["loss_percent"]), "correlation": "100"},
            "duration": f"{int(params['duration_s'])}s",
            "direction": "to",
        })
    elif family == "container_cpu_stress":
        document["kind"] = "StressChaos"
        document["spec"].update({
            "stressors": {"cpu": {
                "workers": int(params["workers"]),
                "load": int(params["load_percent"]),
            }},
            "duration": f"{int(params['duration_s'])}s",
        })
    else:
        raise ValueError(f"unsupported P09 fault family: {family}")
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=False)


def load_selections(selection_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    records = []
    for result_path in sorted(selection_root.rglob("result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        if result.get("status") != "valid" or not isinstance(result.get("selected"), list):
            raise ValueError(f"selection result is not a valid selection: {result_path}")
        records.append((result_path, result))
    if len(records) != 6:
        raise ValueError(f"expected 6 valid selection results, found {len(records)}")
    return records


def materialize(selection_root: Path, pool_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"refusing to overwrite non-empty output directory: {output}")
    pool = json.loads(pool_path.read_text(encoding="utf-8-sig"))
    candidates = {item["candidate_id"]: item for item in pool.get("candidates", [])}
    pool_hash = sha256(pool_path)
    records = load_selections(selection_root)
    output.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    for result_path, result in records:
        arm = str(result["arm"])
        seed = int(result["seed"])
        arm_dir = output / slug(arm) / f"seed-{seed}"
        for selected in result["selected"]:
            candidate_id = str(selected.get("candidate_id", ""))
            rank = int(selected.get("rank", 0))
            if candidate_id not in candidates:
                raise ValueError(f"selected candidate is not in frozen pool: {candidate_id}")
            if rank < 1 or rank > 8:
                raise ValueError(f"invalid selected rank for {candidate_id}: {rank}")
            candidate = candidates[candidate_id]
            identity = f"{arm}:{seed}:{rank}:{candidate_id}"
            identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
            resource_name = f"atlas-p09-sel-{identity_hash}"
            run_dir = arm_dir / f"rank-{rank:02d}-{slug(candidate_id)}"
            run_dir.mkdir(parents=True, exist_ok=True)
            mutation_path = run_dir / f"{resource_name}.yaml"
            mutation_path.write_text(yaml_for(candidate, resource_name), encoding="utf-8")
            provenance = {
                "schema_version": "p09-selection-materialization-v1",
                "project_id": "P09",
                "namespace": NAMESPACE,
                "arm": arm,
                "seed": seed,
                "rank": rank,
                "candidate_id": candidate_id,
                "candidate": candidate,
                "rationale": selected.get("rationale", ""),
                "selection_result_path": str(result_path.resolve()).replace("\\", "/"),
                "selection_result_sha256": sha256(result_path),
                "selection_result_record_sha256": result.get("raw_sha256"),
                "candidate_pool_path": str(pool_path.resolve()).replace("\\", "/"),
                "candidate_pool_sha256": pool_hash,
                "mutation_path": str(mutation_path.resolve()).replace("\\", "/"),
                "mutation_sha256": sha256(mutation_path),
                "human_review": "pending",
                "knowledge_base_updated": False,
            }
            provenance_path = run_dir / "provenance.json"
            provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            runs.append({
                "arm": arm,
                "seed": seed,
                "rank": rank,
                "candidate_id": candidate_id,
                "fault_family": candidate["fault_family"],
                "mutation_path": str(mutation_path.resolve()).replace("\\", "/"),
                "provenance_path": str(provenance_path.resolve()).replace("\\", "/"),
                "human_review": "pending",
                "knowledge_base_updated": False,
            })
    manifest = {
        "schema_version": "p09-selection-materialization-v1",
        "project_id": "P09",
        "namespace": NAMESPACE,
        "selection_root": str(selection_root.resolve()).replace("\\", "/"),
        "candidate_pool": str(pool_path.resolve()).replace("\\", "/"),
        "candidate_pool_sha256": pool_hash,
        "selection_count": len(records),
        "materialized_count": len(runs),
        "human_review": "pending",
        "knowledge_base_updated": False,
        "runs": runs,
    }
    (output / "materialization-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-root", type=Path, default=DEFAULT_SELECTION_ROOT)
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = materialize(args.selection_root, args.pool, args.output)
    print(json.dumps({k: manifest[k] for k in ("selection_count", "materialized_count", "candidate_pool_sha256")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
