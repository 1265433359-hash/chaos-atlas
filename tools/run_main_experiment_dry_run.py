"""Exercise one open-discovery main-track run without an LLM or mutation.

The fixture represents a protocol-valid model response only to verify the
compiler and mutation interfaces.  Its output is explicitly marked as a
dry-run fixture and must never enter experimental metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from open_discovery_compiler import contract_from_topology, compile_output
from open_discovery_mutation_compiler import compile_payload


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_10_projects"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fixture_payload(project_id: str, commit: str, target: str, edge: str | None = None) -> dict[str, Any]:
    target_kind = "dependency_edge" if edge else "service"
    selected = edge or target
    source = edge.split("->", 1)[0] if edge else target
    destination = edge.split("->", 1)[1] if edge else target
    return {
        "method_id": "dry-run-fixture",
        "project_id": project_id,
        "project_commit": commit,
        "hypotheses": [{
            "hypothesis_id": "dry-run-001",
            "target": selected,
            "target_kind": target_kind,
            "fault_family": "network_delay",
            "parameters": {"latency_ms": 100, "duration_s": 10},
            "hypothesis": "A bounded dependency delay may expose an unavailable timeout or fallback boundary.",
            "weakness_surface": f"{source} to {destination}",
            "call_chain": [{"source": source, "target": destination, "relation": "depends_on", "evidence_ref": "topology.edges"}],
            "expected_invariant": "The deterministic business request either preserves its response contract or records a bounded failure.",
            "validation_plan": "Capture baseline, apply one fault, observe the business oracle, remove the fault, verify recovery and cleanup.",
            "recovery_expectation": "The namespace returns healthy and no Chaos Mesh resource remains after removal.",
        }],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="P02")
    parser.add_argument("--seed", type=int, default=1001)
    parser.add_argument("--output-dir", type=Path, default=EXPERIMENT / "main_experiment_dry_run" / "P02" / "seed-1001")
    args = parser.parse_args()

    common = read_json(EXPERIMENT / "input_bundles" / args.project / f"seed-{args.seed}" / "common.json")
    topology = read_json(EXPERIMENT / "topology_profiles" / args.project / "topology.json")
    runtime_map_path = EXPERIMENT / "runtime_profiles" / args.project / "runtime-map.json"
    runtime_map = read_json(runtime_map_path) if runtime_map_path.exists() else {}
    namespace = f"chaosatlas-{args.project.lower()}"
    contract = contract_from_topology(
        args.project,
        common["project_commit"],
        namespace,
        f"{args.project}-primary-workload",
        common["workload_summary"]["health"],
        topology,
    )
    target = "compose/service/api-gateway"
    destination = "compose/service/config-server"
    payload = fixture_payload(args.project, common["project_commit"], target, f"{target}->{destination}")
    compiled = compile_output(payload, contract)
    mutations = compile_payload(compiled, topology, runtime_map)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "fixture_payload.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "compiled.json").write_text(json.dumps(compiled, indent=2) + "\n", encoding="utf-8")
    mutation_manifest = dict(mutations)
    for entry in mutation_manifest.get("generated", []):
        name = f"{entry['canonical_signature'][:12]}"
        yaml_path = args.output_dir / f"{name}.yaml"
        provenance_path = args.output_dir / f"{name}.provenance.json"
        yaml_path.write_text(entry["yaml"], encoding="utf-8")
        provenance = dict(entry["provenance"])
        provenance.update({"yaml_path": str(yaml_path.relative_to(ROOT)).replace("\\", "/"), "yaml_sha256": sha256(entry["yaml"]), "dry_run_fixture": True})
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        entry["yaml_path"] = str(yaml_path.relative_to(ROOT)).replace("\\", "/")
        entry["provenance_path"] = str(provenance_path.relative_to(ROOT)).replace("\\", "/")
    mutation_manifest.update({"dry_run_fixture": True, "llm_called": False, "mutation_applied": False, "created_at": datetime.now(timezone.utc).isoformat()})
    (args.output_dir / "mutation_manifest.json").write_text(json.dumps(mutation_manifest, indent=2) + "\n", encoding="utf-8")
    summary = {
        "project_id": args.project,
        "seed": args.seed,
        "compiled_status": compiled.get("status"),
        "accepted": compiled.get("accepted_count", 0),
        "rejected": compiled.get("rejected_count", 0),
        "mutation_status": mutations.get("status"),
        "generated": mutations.get("generated_count", 0),
        "dry_run_fixture": True,
        "llm_called": False,
        "mutation_applied": False,
        "output_dir": str(args.output_dir),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if compiled.get("status") == "valid" and mutations.get("status") == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
