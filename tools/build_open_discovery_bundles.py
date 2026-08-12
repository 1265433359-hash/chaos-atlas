"""Build secret-free open-discovery bundles from frozen project evidence.

The existing candidate-ranking bundles are never overwritten. This builder
removes candidate-pool fields before writing the v2 open-discovery inputs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.open_discovery_prompts import (
        CHAOSATLAS_OPEN_SYSTEM,
        CHAOSATLAS_OPEN_USER,
        CHAOSEATER_OPEN_SYSTEM,
        CHAOSEATER_OPEN_USER,
        OPEN_OUTPUT_SCHEMA,
    )
except ModuleNotFoundError:  # direct `python tools/script.py` invocation
    from open_discovery_prompts import (
        CHAOSATLAS_OPEN_SYSTEM,
        CHAOSATLAS_OPEN_USER,
        CHAOSEATER_OPEN_SYSTEM,
        CHAOSEATER_OPEN_USER,
        OPEN_OUTPUT_SCHEMA,
    )


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_10_projects"
SOURCE = EXPERIMENT / "input_bundles"
OUT = EXPERIMENT / "open_discovery_bundles"
TOPOLOGY_ROOT = EXPERIMENT / "topology_profiles"
PROTOCOL = EXPERIMENT / "protocol_v2_open_discovery.md"
PROMPTS = ROOT / "tools/open_discovery_prompts.py"
PROJECTS = [f"P{index:02d}" for index in range(1, 11)]
SEEDS = [1001, 1002, 1003]
ARMS = ["ChaosAtlas-KB-open", "ChaosAtlas-noKB-open", "ChaosEater-open", "ChaosEater-adapter-open"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def common_view(common: dict[str, Any]) -> dict[str, Any]:
    source = common.get("common_input", common)
    keep = ("schema_version", "project_id", "project_commit", "source_tree_sha", "deployment_summary", "workload_summary", "runner_version", "oracle_version")
    return {key: source[key] for key in keep}


def topology_view(project_id: str) -> dict[str, Any]:
    path = TOPOLOGY_ROOT / project_id / "topology.json"
    if not path.exists():
        return {"status": "topology_unavailable", "reason": "no frozen YAML/Compose evidence was found"}
    source = load(path)
    # Keep the graph and defense attributes, but never copy source file text or
    # values that could become an oracle channel.
    return {
        "status": "available" if source.get("nodes") else ("topology_unavailable" if not source.get("supported_document_count") else "topology_empty"),
        "graph_hash": source.get("graph_hash"),
        "nodes": source.get("nodes", []),
        "edges": source.get("edges", []),
        "defenses": source.get("defenses", []),
        "supported_document_count": source.get("supported_document_count", 0),
        "source_sha256": sha256(path),
    }


def runtime_contract(project_id: str) -> dict[str, Any]:
    return {
        "namespace": f"chaosatlas-{project_id.lower()}",
        "workload_id": f"{project_id}-primary-workload",
        "max_hypotheses": 8,
        "fault_families": ["pod_kill", "network_delay", "network_loss", "container_cpu_stress"],
        "parameter_bounds": {
            "network_delay": {"latency_ms": [1, 500], "duration_s": [1, 60]},
            "network_loss": {"loss_percent": [1, 100], "duration_s": [1, 60]},
            "container_cpu_stress": {"workers": [1, 2], "load_percent": [1, 80], "duration_s": [1, 60]},
            "pod_kill": {"mode": ["one"]},
        },
        "namespace_scope": "all mutations must resolve inside the project namespace",
        "target_resolution": "target must be a node or edge in topology_evidence; unresolved targets are rejected",
        "lifecycle": ["clean", "health_gate", "baseline", "apply_one_fault", "verify_injection", "observe", "remove_fault", "recovery_health", "cleanup"],
        "required_result_classes": ["confirmed_weakness", "protected", "latent_risk", "unsupported", "environment_blocked", "method_invalid"],
        "execution_policy": "compiler and runtime resolver fail closed; no shell or kubectl commands in model output",
    }


def build_bundle(project_id: str, seed: int, arm: str) -> dict[str, Any]:
    source = load(SOURCE / project_id / f"seed-{seed}" / "common.json")
    topology = topology_view(project_id)
    bundle: dict[str, Any] = {
        "schema_version": "2.0",
        "protocol": "protocol_v2_open_discovery.md",
        "arm": arm,
        "project_id": project_id,
        "seed": seed,
        "primary_track": True,
        "common_input": common_view(source),
        "topology_evidence": topology,
        "runtime_contract": runtime_contract(project_id),
        "knowledge_view": None,
        "candidate_pool_visible": False,
        "candidate_order_visible": False,
        "output_schema": "open_discovery_schema.json",
        "prompt_module_sha256": sha256(PROMPTS),
        "source_evidence_sha256": sha256(SOURCE / project_id / f"seed-{seed}" / "common.json"),
        "topology_evidence_sha256": topology.get("source_sha256"),
    }
    if arm == "ChaosAtlas-KB-open":
        knowledge_path = EXPERIMENT / "knowledge_cards" / project_id / "knowledge_card.json"
        bundle["knowledge_view"] = {"ref": f"knowledge_cards/{project_id}/knowledge_card.json", "sha256": sha256(knowledge_path), "content": load(knowledge_path)}
    elif arm == "ChaosAtlas-noKB-open":
        bundle["knowledge_view"] = None
    else:
        bundle["method_contract"] = "ChaosEater FaultScenarioAgent open mode; no ChaosAtlas knowledge"
    serialized = json.dumps(bundle, ensure_ascii=True)
    forbidden = ('"candidate_pool":', '"candidate_order":', '"candidate_id":', '"oracle_label":', '"runtime_observation":', '"post_run_rca":', '"mutation_path":', '"shell_command":', '"kubectl_command":')
    if any(term in serialized for term in forbidden):
        raise ValueError(f"forbidden open-bundle term for {project_id}/{seed}/{arm}")
    return bundle


def render_prompt(bundle: dict[str, Any]) -> str:
    evidence = json.dumps({"common_input": bundle["common_input"], "topology_evidence": bundle["topology_evidence"]}, indent=2, ensure_ascii=True)
    runtime = json.dumps(bundle["runtime_contract"], indent=2, ensure_ascii=True)
    knowledge = json.dumps(bundle.get("knowledge_view"), indent=2, ensure_ascii=True)
    if bundle["arm"].startswith("ChaosAtlas"):
        system = CHAOSATLAS_OPEN_SYSTEM
        if bundle["arm"] == "ChaosAtlas-noKB-open":
            user = ("PROJECT EVIDENCE\n" + evidence + "\n\nRUNTIME SAFETY CONTRACT\n" + runtime +
                    "\n\nOUTPUT SCHEMA\n" + OPEN_OUTPUT_SCHEMA +
                    "\n\nPropose at most 8 distinct hypotheses. The candidate pool is intentionally not provided; use the project evidence to identify targets and mechanisms.")
        else:
            user = CHAOSATLAS_OPEN_USER.format(project_evidence=evidence, runtime_contract=runtime, knowledge_view=knowledge, output_schema=OPEN_OUTPUT_SCHEMA, max_hypotheses=8)
    else:
        system = CHAOSEATER_OPEN_SYSTEM
        user = CHAOSEATER_OPEN_USER.format(project_evidence=evidence, runtime_contract=runtime, output_schema=OPEN_OUTPUT_SCHEMA, max_hypotheses=8)
    prompt = system.rstrip() + "\n\n===== USER =====\n" + user.rstrip() + "\n"
    if "candidate_id" in prompt or "candidate_pool" in prompt or "candidate_order" in prompt:
        raise ValueError(f"candidate control text leaked into open prompt: {bundle['project_id']}/{bundle['seed']}/{bundle['arm']}")
    return prompt


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    prompt_files: list[str] = []
    audits: list[dict[str, Any]] = []
    for project_id in PROJECTS:
        for seed in SEEDS:
            for arm in ARMS:
                output_dir = OUT / project_id / f"seed-{seed}"
                output_dir.mkdir(parents=True, exist_ok=True)
                output = output_dir / f"{arm.lower()}.json"
                output.write_text(json.dumps(build_bundle(project_id, seed, arm), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
                files.append(str(output.relative_to(ROOT)).replace("\\", "/"))
                bundle = load(output)
                prompt = output_dir / f"{arm.lower()}.prompt.txt"
                prompt.write_text(render_prompt(bundle), encoding="utf-8")
                prompt_files.append(str(prompt.relative_to(ROOT)).replace("\\", "/"))
                audits.append({"project_id": project_id, "seed": seed, "arm": arm, "forbidden_hits": 0, "sha256": sha256(output)})
    manifest = {
        "schema_version": "2.0",
        "kind": "open_discovery_input_manifest",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol": str(PROTOCOL.relative_to(ROOT)).replace("\\", "/"),
        "projects": PROJECTS,
        "seeds": SEEDS,
        "arms": ARMS,
        "candidate_pool_visible": False,
        "candidate_pool_used_only_post_compilation": True,
        "no_llm_called": True,
        "files": files,
        "prompt_files": prompt_files,
        "audit": audits,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(files), "audits": len(audits), "no_llm_called": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
