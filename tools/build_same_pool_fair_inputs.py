"""Build result-free same-candidate-pool inputs for the three real projects."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


SEEDS = (1001, 1002, 1003)
METHODS = ("ChaosAtlas-full", "ChaosAtlas-ablation", "ChaosEater-adapter")
RULE_VERSION = "same-pool-fair-candidates-v1"
DEFAULT_OUT = Path("artifacts/experiments/chaosatlas_same_pool_fair_2026-08-14-r1")

PROJECTS: dict[str, dict[str, Any]] = {
    "online-boutique": {
        "namespace": "chaosatlas-online-boutique",
        "label_key": "app",
        "targets": (
            "adservice",
            "cartservice",
            "checkoutservice",
            "currencyservice",
            "emailservice",
            "frontend",
            "paymentservice",
            "productcatalogservice",
            "recommendationservice",
            "redis-cart",
            "shippingservice",
        ),
        "oracle": "checkout PlaceOrder through checkoutservice/cartservice port-forward",
    },
    "opentelemetry-demo": {
        "namespace": "chaosatlas-otel",
        "label_key": "app",
        "targets": (
            "cart",
            "checkout",
            "currency",
            "email",
            "flagd",
            "payment",
            "postgres",
            "product-catalog",
            "quote",
            "shipping",
            "valkey",
        ),
        "oracle": "checkout PlaceOrder through checkout/cart port-forward",
    },
    "sock-shop": {
        "namespace": "chaosatlas-sock-shop",
        "label_key": "name",
        "targets": (
            "carts",
            "carts-db",
            "catalogue",
            "catalogue-db",
            "front-end",
            "orders",
            "orders-db",
            "payment",
            "queue-master",
            "rabbitmq",
            "session-db",
            "shipping",
            "user",
            "user-db",
        ),
        "oracle": "front-end golden journey: front page, catalogue, login, orders",
    },
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _yaml_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _metadata_name(project_id: str, target: str, fault_family: str, parameters: dict[str, Any]) -> str:
    digest = _sha256({"project": project_id, "target": target, "fault": fault_family, "parameters": parameters})[:12]
    return f"atlas-fair-{project_id}-{digest}"[:63]


def _network_yaml(project_id: str, config: dict[str, Any], target: str, fault_family: str, parameters: dict[str, Any]) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "mode": "one",
        "selector": {
            "namespaces": [config["namespace"]],
            "labelSelectors": {config["label_key"]: target},
        },
        "duration": parameters["duration"],
        "direction": "to",
    }
    if fault_family == "network_loss":
        spec.update({"action": "loss", "loss": {"loss": str(parameters["loss"]), "correlation": "100"}})
    elif fault_family == "network_delay":
        spec.update({"action": "delay", "delay": {"latency": parameters["latency"], "correlation": "100", "jitter": "0ms"}})
    else:  # pragma: no cover - caller controls fault family
        raise ValueError(f"unsupported network fault: {fault_family}")
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "NetworkChaos",
        "metadata": {
            "name": _metadata_name(project_id, target, fault_family, parameters),
            "namespace": config["namespace"],
            "labels": {
                "chaosatlas.dev/project": project_id,
                "chaosatlas.dev/generator": RULE_VERSION,
            },
        },
        "spec": spec,
    }


def _podkill_yaml(project_id: str, config: dict[str, Any], target: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {
            "name": _metadata_name(project_id, target, "pod_kill", parameters),
            "namespace": config["namespace"],
            "labels": {
                "chaosatlas.dev/project": project_id,
                "chaosatlas.dev/generator": RULE_VERSION,
            },
        },
        "spec": {
            "action": "pod-kill",
            "mode": "one",
            "selector": {
                "namespaces": [config["namespace"]],
                "labelSelectors": {config["label_key"]: target},
            },
        },
    }


def _stress_yaml(project_id: str, config: dict[str, Any], target: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "StressChaos",
        "metadata": {
            "name": _metadata_name(project_id, target, "container_cpu_stress", parameters),
            "namespace": config["namespace"],
            "labels": {
                "chaosatlas.dev/project": project_id,
                "chaosatlas.dev/generator": RULE_VERSION,
            },
        },
        "spec": {
            "mode": "one",
            "selector": {
                "namespaces": [config["namespace"]],
                "labelSelectors": {config["label_key"]: target},
            },
            "stressors": {"cpu": {"workers": parameters["workers"], "load": parameters["load"]}},
            "duration": parameters["duration"],
        },
    }


def _candidate_yaml(project_id: str, config: dict[str, Any], target: str, fault_family: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if fault_family in {"network_loss", "network_delay"}:
        return _network_yaml(project_id, config, target, fault_family, parameters)
    if fault_family == "pod_kill":
        return _podkill_yaml(project_id, config, target, parameters)
    if fault_family == "container_cpu_stress":
        return _stress_yaml(project_id, config, target, parameters)
    raise ValueError(f"unsupported fault family: {fault_family}")


def build_candidate_pool() -> dict[str, list[dict[str, Any]]]:
    pool: dict[str, list[dict[str, Any]]] = {}
    fault_specs = (
        ("network_loss", {"loss": 100, "duration": "30s"}),
        ("network_delay", {"latency": "500ms", "duration": "30s"}),
        ("network_delay", {"latency": "2000ms", "duration": "30s"}),
        ("pod_kill", {"mode": "one"}),
        ("container_cpu_stress", {"workers": 1, "load": 80, "duration": "30s"}),
    )
    for project_id, config in PROJECTS.items():
        candidates: list[dict[str, Any]] = []
        for target in config["targets"]:
            for fault_family, parameters in fault_specs:
                doc = _candidate_yaml(project_id, config, target, fault_family, parameters)
                yaml_text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=False)
                signature = _sha256({"project": project_id, "target": target, "fault_family": fault_family, "parameters": parameters})
                candidates.append({
                    "candidate_id": f"{project_id}:{target}:{fault_family}:{signature[:12]}",
                    "project_id": project_id,
                    "namespace": config["namespace"],
                    "target": target,
                    "selector": {config["label_key"]: target},
                    "fault_family": fault_family,
                    "parameters": parameters,
                    "business_oracle": config["oracle"],
                    "yaml": yaml_text,
                    "yaml_sha256": _yaml_sha256(yaml_text),
                    "generation_rule": RULE_VERSION,
                })
        pool[project_id] = sorted(candidates, key=lambda item: item["candidate_id"])
    return pool


def _knowledge_view(method: str) -> dict[str, Any] | None:
    if method == "ChaosAtlas-full":
        return {
            "schema_version": "same-pool-chaosatlas-full-knowledge-v1",
            "human_review": "pending",
            "knowledge_scope": "generic_patterns_only",
            "facts": [
                "single replica workloads are high-value PodKill candidates",
                "synchronous downstream calls without evidenced bounds are high-value loss/delay candidates",
                "side-effect services can still block primary business flows if synchronously coupled",
            ],
        }
    if method == "ChaosEater-adapter":
        return {
            "schema_version": "same-pool-chaoseater-adapter-view-v1",
            "style": "chaoseater_adapter",
            "instruction": "rank candidates using steady-state disruption hypotheses and experiment feasibility; do not use ChaosAtlas knowledge",
        }
    return None


def write_freeze(output_root: Path) -> dict[str, Any]:
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing non-empty directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    pool = build_candidate_pool()
    records: list[dict[str, Any]] = []
    pool_hashes: dict[str, str] = {}
    for project_id, candidates in pool.items():
        pool_dir = output_root / "candidate_pools" / project_id
        yaml_dir = pool_dir / "mutations"
        yaml_dir.mkdir(parents=True, exist_ok=True)
        public_candidates = []
        for candidate in candidates:
            yaml_name = f"{candidate['candidate_id'].split(':')[-1]}.yaml"
            yaml_path = yaml_dir / yaml_name
            yaml_path.write_text(candidate["yaml"], encoding="utf-8")
            item = {key: value for key, value in candidate.items() if key != "yaml"}
            item["yaml_path"] = str(yaml_path.relative_to(output_root)).replace("\\", "/")
            item["yaml_sha256"] = hashlib.sha256(yaml_path.read_bytes()).hexdigest()
            public_candidates.append(item)
        pool_sha = _sha256(public_candidates)
        pool_hashes[project_id] = pool_sha
        (pool_dir / "candidates.json").write_text(json.dumps(public_candidates, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        records.append({"project_id": project_id, "candidate_count": len(public_candidates), "candidate_pool_sha256": pool_sha})
        for seed in SEEDS:
            seed_dir = output_root / "method_inputs" / project_id / f"seed-{seed}"
            seed_dir.mkdir(parents=True, exist_ok=True)
            for method in METHODS:
                payload = {
                    "schema_version": "chaosatlas-same-pool-method-input-v1",
                    "project_id": project_id,
                    "seed": seed,
                    "method_id": method,
                    "candidate_pool_sha256": pool_sha,
                    "candidate_pool": public_candidates,
                    "selection_budget": 4,
                    "replicates_per_candidate": 2,
                    "knowledge_view": _knowledge_view(method),
                    "human_review": "pending",
                    "knowledge_base_updated": False,
                }
                (seed_dir / f"{method}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "chaosatlas-same-pool-fair-freeze-v1",
        "projects": sorted(pool),
        "methods": list(METHODS),
        "seeds": list(SEEDS),
        "generation_rule": RULE_VERSION,
        "records": records,
        "pool_sha256": _sha256(records),
        "model_calls": False,
        "runtime_started": False,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    result = write_freeze(args.output)
    print(json.dumps({"status": "completed", "output": str(args.output), "pool_sha256": result["pool_sha256"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
