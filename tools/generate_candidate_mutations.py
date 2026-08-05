"""Generate bounded, auditable mutation YAMLs from a candidate selection report."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_name(value: str, max_length: int = 63) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return normalized[:max_length].rstrip("-") or "chaos-candidate"


def source_path(relative: str) -> Path:
    return ROOT / relative.replace("\\", "/")


def generate(candidate: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any] | None, str | None]:
    if candidate.get("decision") != args.require_decision:
        return None, f"decision is {candidate.get('decision')}, not {args.require_decision}"
    source = source_path(str(candidate.get("source_yaml", "")))
    if not source.exists():
        return None, f"source YAML does not exist: {source}"
    actual_hash = sha256(source)
    expected_hash = candidate.get("source_sha256")
    if expected_hash and expected_hash != actual_hash:
        return None, "source SHA-256 does not match the selection report"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None, "source YAML root is not a mapping"
    kind = str(raw.get("kind", candidate.get("kind", "")))
    app = candidate.get("target_app")
    if not app:
        return None, "candidate has no target_app"
    metadata = raw.setdefault("metadata", {})
    spec = raw.setdefault("spec", {})
    rank = int(candidate.get("rank", 0) or 0)
    base_name = str(candidate.get("raw_name") or metadata.get("name") or candidate.get("test_id") or kind)
    metadata["name"] = safe_name(f"{base_name}-candidate-r{rank}")
    metadata["namespace"] = args.namespace
    metadata["annotations"] = {
        **(metadata.get("annotations") or {}),
        "chaos.origin.raw-sha256": actual_hash,
        "chaos.origin.source-yaml": str(candidate.get("source_yaml")),
        "chaos.candidate.decision": str(candidate.get("decision")),
        "chaos.candidate.rank": str(rank),
    }
    metadata["labels"] = {
        **(metadata.get("labels") or {}),
        "chaos.generated": "candidate",
        "chaos.test-node": next(
            (str(value) for value in (candidate.get("test_nodes") or []) if value != "selector"),
            "unknown",
        ),
    }
    selector = spec.setdefault("selector", {})
    selector["namespaces"] = [args.namespace]
    selector["labelSelectors"] = {"app": app}
    spec["mode"] = "one"

    nodes = set(candidate.get("test_nodes") or [])
    if kind == "NetworkChaos" and "network_delay" in nodes:
        if not isinstance(spec.get("delay"), dict):
            return None, "NetworkChaos candidate has no delay block"
        spec["delay"]["latency"] = args.network_latency
        spec["duration"] = args.network_duration
    elif kind == "StressChaos" and "stress_cpu" in nodes:
        stressors = spec.get("stressors")
        if not isinstance(stressors, dict) or not isinstance(stressors.get("cpu"), dict):
            return None, "StressChaos candidate has no CPU stressor block"
        stressors["cpu"]["workers"] = args.stress_workers
        stressors["cpu"]["load"] = args.stress_load
        spec["duration"] = args.stress_duration
    elif kind == "HTTPChaos":
        spec["duration"] = args.http_duration
    else:
        return None, f"no bounded mutation policy for kind/test nodes: {kind}/{sorted(nodes)}"

    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    destination = output_dir / f"{metadata['name']}.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return {
        "candidate_rank": rank,
        "test_id": candidate.get("test_id"),
        "kind": kind,
        "test_nodes": sorted(nodes),
        "target_app": app,
        "source_yaml": candidate.get("source_yaml"),
        "source_sha256": actual_hash,
        "mutation_yaml": str(destination.relative_to(ROOT)).replace("\\", "/"),
        "namespace": args.namespace,
        "name": metadata["name"],
        "policy": {
            "mode": "one",
            "bounded_duration": spec.get("duration"),
            "runner": "tools/run_chaos_experiment.py",
            "requires_gate": "tools/runtime_applicability_gate.py",
            "not_applied_by_generator": True,
        },
    }, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--namespace", default="train-ticket-lab")
    parser.add_argument("--require-decision", default="ready_candidate_with_runner")
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument("--network-latency", default="100ms")
    parser.add_argument("--network-duration", default="20s")
    parser.add_argument("--stress-workers", type=int, default=1)
    parser.add_argument("--stress-load", type=int, default=80)
    parser.add_argument("--stress-duration", default="45s")
    parser.add_argument("--http-duration", default="20s")
    args = parser.parse_args()

    selection = load_json(args.selection)
    candidates = selection.get("candidates") or []
    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(generated) >= max(0, args.max_candidates):
            break
        result, error = generate(candidate, args)
        if result:
            generated.append(result)
        else:
            skipped.append({"test_id": candidate.get("test_id"), "reason": error})
    plan = {
        "schema_version": 1,
        "tool": "generate_candidate_mutations",
        "selection_report": str(args.selection).replace("\\", "/"),
        "namespace": args.namespace,
        "generated_count": len(generated),
        "generated": generated,
        "skipped": skipped,
        "safety": {
            "apply_performed": False,
            "source_hash_preserved": True,
            "selector_rewritten_to_isolated_namespace": True,
            "next_command": "run runtime_applicability_gate.py, then run_chaos_experiment.py",
        },
    }
    args.plan.parent.mkdir(parents=True, exist_ok=True)
    args.plan.write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
