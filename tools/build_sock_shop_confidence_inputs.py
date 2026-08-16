from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.yaml_confidence_categories import (
    load_yaml_feature_rows,
    summarize_feature_rows,
)


METHODS: dict[str, dict[str, Any]] = {
    "native-full": {
        "knowledge_allowed": True,
        "allowed_inputs": [
            "sock_shop_deployment_facts",
            "service_topology",
            "business_oracle",
            "complete_project_knowledge",
            "knowledge_base",
            "historical_experience",
            "call_chain_projection",
        ],
        "forbidden_inputs": [],
    },
    "chaosatlas-ablation": {
        "knowledge_allowed": False,
        "allowed_inputs": [
            "sock_shop_deployment_facts",
            "service_topology",
            "business_oracle",
            "yaml_category_statistics",
        ],
        "forbidden_inputs": [
            "knowledge_base",
            "historical_weakness_evidence",
            "call_chain_projection",
            "full_projection",
        ],
    },
}

SOCK_SHOP_SERVICES = [
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
]

NATIVE_KNOWLEDGE_PATH = ROOT / "artifacts" / "sock-shop" / "sock_knowledge_snapshot_static.json"


def _load_native_project_knowledge() -> dict[str, Any]:
    if not NATIVE_KNOWLEDGE_PATH.is_file():
        raise FileNotFoundError(f"native-full knowledge snapshot is missing: {NATIVE_KNOWLEDGE_PATH}")
    source_bytes = NATIVE_KNOWLEDGE_PATH.read_bytes()
    snapshot = json.loads(source_bytes.decode("utf-8"))
    contracts = ((snapshot.get("contract") or {}).get("contracts") or {})
    edges = []
    for edge_id, contract in sorted(contracts.items()):
        if "->" not in edge_id:
            continue
        source, target = edge_id.rsplit("->", 1)
        edges.append(
            {
                "edge_id": edge_id,
                "source": source,
                "target": target,
                "contract": contract,
            }
        )

    source_path = str(NATIVE_KNOWLEDGE_PATH.relative_to(ROOT)).replace("\\", "/")
    complete = {
        "source_path": source_path,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "schema_version": snapshot.get("schema_version"),
        "provenance": snapshot.get("provenance"),
        "source_provenance": snapshot.get("source_provenance"),
        "contract": snapshot.get("contract"),
        "selection_experience": snapshot.get("selection_experience"),
        "defense_pattern_library": snapshot.get("defense_pattern_library"),
        "judgment_experience": snapshot.get("judgment_experience"),
    }
    return {
        "complete_project_knowledge": complete,
        "knowledge_projection": {
            "source_path": source_path,
            "source_sha256": complete["source_sha256"],
            "provenance": complete["provenance"],
            "contract": complete["contract"],
            "availability": (complete["contract"] or {}).get("availability", {}),
            "source_provenance": complete["source_provenance"],
        },
        "knowledge_base_view": {
            "source_path": source_path,
            "source_sha256": complete["source_sha256"],
            "selection_experience": complete["selection_experience"],
            "defense_pattern_library": complete["defense_pattern_library"],
        },
        "historical_experience": {
            "source_path": source_path,
            "source_sha256": complete["source_sha256"],
            "judgment_experience": complete["judgment_experience"],
        },
        "call_chain_projection": {
            "source_path": source_path,
            "source_sha256": complete["source_sha256"],
            "edges": edges,
            "edge_count": len(edges),
        },
    }


def _ensure_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _classification_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Sock Shop YAML Confidence Classification Report",
        "",
        f"- total_yaml: {summary['total_yaml']}",
        f"- included_runtime_scope: {summary['included_runtime_scope']}",
        f"- excluded_from_runtime_scope: {summary['excluded_from_runtime_scope']}",
        "- human_review: pending",
        "- knowledge_base_updated: false",
        "",
        "| category | count | min | max | tau | coverage_target |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for category, data in summary["categories"].items():
        lines.append(
            "| {category} | {count} | {min_hypotheses} | {max_hypotheses} | {tau} | {coverage_target} |".format(
                category=category,
                **data,
            )
        )
    lines.extend(
        [
            "",
            "Low-frequency kinds are retained in the inventory but excluded from this runtime scope.",
        ]
    )
    return "\n".join(lines) + "\n"


def _feature_motifs(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        category: {
            "top_motifs": data["top_motifs"],
            "pairwise_lift": data["pairwise_lift"],
        }
        for category, data in summary["categories"].items()
    }


def _initial_timing() -> dict[str, float | None]:
    return {
        "yaml_statistics_seconds": None,
        "generation_seconds": None,
        "compile_seconds": None,
        "gate_seconds": None,
        "runtime_seconds": None,
        "washout_seconds": None,
        "summary_seconds": None,
        "total_wall_clock_seconds": None,
    }


def build_confidence_input_manifest(
    raw_yaml_root: Path,
    output_dir: Path,
    sock_shop_profile: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    _ensure_output_dir(output_dir)
    started = time.monotonic()
    rows = load_yaml_feature_rows(raw_yaml_root)
    summary = summarize_feature_rows(rows)
    yaml_statistics_seconds = round(time.monotonic() - started, 3)

    _write_json(output_dir / "yaml_inventory.json", rows)
    _write_json(output_dir / "category_summary.json", summary)
    _write_json(output_dir / "yaml-category-summary.json", summary)
    _write_json(output_dir / "feature_distribution.json", summary["categories"])
    _write_json(output_dir / "feature_motifs.json", _feature_motifs(summary))
    confidence_protocol = {
        "schema_version": "sock-shop-yaml-confidence-protocol-v2",
        "source": "frozen YAML category features",
        "runtime_outcomes_used": False,
        "categories": {
            category: {
                "count": data["count"],
                "feature_entropy": data["feature_entropy"],
                "feature_complexity": data["feature_complexity"],
                "min_hypotheses": data["min_hypotheses"],
                "max_hypotheses": data["max_hypotheses"],
                "tau": data["tau"],
                "coverage_target": data["coverage_target"],
                "confidence_policy": data["confidence_policy"],
            }
            for category, data in summary["categories"].items()
        },
    }
    protocol_path = output_dir / "confidence_protocol.json"
    _write_json(protocol_path, confidence_protocol)
    (output_dir / "classification_report.md").write_text(
        _classification_report(summary),
        encoding="utf-8",
    )

    manifest_methods: dict[str, Any] = {}
    native_knowledge = _load_native_project_knowledge()
    for method, method_config in METHODS.items():
        timing = _initial_timing()
        timing["yaml_statistics_seconds"] = yaml_statistics_seconds
        method_payload = {
            "experiment": "sock_shop_yaml_confidence",
            "method": method,
            "knowledge_allowed": method_config["knowledge_allowed"],
            "allowed_inputs": method_config["allowed_inputs"],
            "forbidden_inputs": method_config["forbidden_inputs"],
            "yaml_category_summary": summary,
            "sock_shop_profile": sock_shop_profile,
            "timing": timing,
            "human_review": "pending",
            "knowledge_base_updated": False,
        }
        if method == "native-full":
            method_payload.update(native_knowledge)
        _write_json(output_dir / "method-inputs" / f"{method}.json", method_payload)
        manifest_methods[method] = {
            "input_path": str(Path("method-inputs") / f"{method}.json"),
            "knowledge_allowed": method_config["knowledge_allowed"],
            "allowed_inputs": method_config["allowed_inputs"],
            "forbidden_inputs": method_config["forbidden_inputs"],
        }

    total_wall_clock_seconds = max(
        yaml_statistics_seconds,
        round(time.monotonic() - started, 3),
    )

    manifest = {
        "experiment": "sock_shop_yaml_confidence",
        "raw_yaml_root": str(raw_yaml_root),
        "total_yaml": summary["total_yaml"],
        "included_runtime_scope": summary["included_runtime_scope"],
        "confidence_protocol_path": str(protocol_path.relative_to(output_dir)),
        "confidence_protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "human_review": "pending",
        "knowledge_base_updated": False,
        "methods": manifest_methods,
        "native_knowledge_source": {
            "path": native_knowledge["complete_project_knowledge"]["source_path"],
            "sha256": native_knowledge["complete_project_knowledge"]["source_sha256"],
            "provenance": native_knowledge["complete_project_knowledge"]["provenance"],
        },
        "dry_run": dry_run,
        "timing": {
            "yaml_statistics_seconds": yaml_statistics_seconds,
            "total_wall_clock_seconds": total_wall_clock_seconds,
        },
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _load_profile(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "namespace": "chaosatlas-sock-shop",
            "services": SOCK_SHOP_SERVICES,
            "oracles": ["authenticated-orders-journey"],
            "business_oracle": {
                "workflow": "front-end home, catalogue browse, demo login, and authenticated orders read-only golden journey",
                "paths": ["/", "/catalogue", "/login", "/orders"],
            },
        }
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-yaml", type=Path, default=Path("raw_yaml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sock-shop-profile", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest = build_confidence_input_manifest(
        raw_yaml_root=args.raw_yaml,
        output_dir=args.output,
        sock_shop_profile=_load_profile(args.sock_shop_profile),
        dry_run=args.dry_run,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
