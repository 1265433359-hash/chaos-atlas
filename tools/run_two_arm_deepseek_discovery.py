"""Run the authorized two-arm DeepSeek discovery matrix without runtime mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("ChaosAtlas-full", "ChaosAtlas-ablation")
SEEDS = (1001, 1002, 1003)
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
FAULT_FAMILIES = ("pod_kill", "network_delay", "network_loss", "container_cpu_stress")


def topology_fault_family_contract(bundle: dict[str, Any]) -> dict[str, list[str]]:
    topology = ((bundle.get("common_input") or {}).get("topology") or {})
    contract: dict[str, list[str]] = {}
    for node in topology.get("nodes", []):
        if not isinstance(node, dict):
            continue
        target = str(node.get("id", ""))
        role = str(node.get("role", ""))
        if target and role in {"workload", "routing", "entrypoint"}:
            allowed = FAULT_FAMILIES if role == "workload" else ("network_delay", "network_loss")
            contract[target] = sorted(allowed)
    for edge in topology.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("source", "")), str(edge.get("target", ""))
        if source in contract and target in contract:
            contract[f"{source}->{target}"] = ["network_delay", "network_loss"]
    return dict(sorted(contract.items()))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def redact_secret(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED]") if secret else value


def validate_response_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("model response must be an object")
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) > 8:
        raise ValueError("hypotheses must be a list of at most 8")
    return value


def build_messages(bundle: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are the ChaosAtlas discovery analyst. Use only the supplied frozen "
        "topology and business oracle. Return only JSON with at most eight bounded "
        "hypotheses. Do not invent commands, runtime observations, RCA, candidate "
        "identifiers, or knowledge outside the provided knowledge_view. Use exact "
        "topology IDs and namespace-local fault parameters. target_kind must be "
        "exactly service or dependency_edge. call_chain must be an array of link "
        "objects, each with source, target, relation, and evidence_ref, using exact "
        "topology IDs. Use only the allowed_fault_families supplied below for each "
        "target. pod_kill is permitted only for workload targets."
    )
    user = json.dumps({
        "method_id": bundle.get("method_id"),
        "seed": bundle.get("seed"),
        "common_input": bundle.get("common_input"),
        "knowledge_view": bundle.get("knowledge_view"),
        "allowed_fault_families": topology_fault_family_contract(bundle),
            "output_schema": {
            "project_id": "exact project id",
            "project_commit": "exact 40 hex commit",
            "hypotheses": "list of <=8 objects with hypothesis_id,target,target_kind,fault_family,parameters,hypothesis,weakness_surface,call_chain,expected_invariant,validation_plan,recovery_expectation",
            "no_safe_hypothesis_reason": "required when hypotheses is empty",
                "target_kind": "exactly service or dependency_edge",
                "call_chain": [{"source": "exact topology node id", "target": "exact topology node id", "relation": "topology relation", "evidence_ref": "topology"}],
            },
        "parameter_contract": {
            "pod_kill": {"mode": "one"},
            "network_delay": {"latency_ms": "integer 1..500", "duration_s": "integer 1..60"},
            "network_loss": {"loss_percent": "integer 1..100", "duration_s": "integer 1..60"},
            "container_cpu_stress": {"workers": "integer 1..2", "load_percent": "integer 1..80", "duration_s": "integer 1..60"},
        },
    }, indent=2, ensure_ascii=True)
    return system, user


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    return validate_response_shape(json.loads(text))


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def bundle_path_for(input_root: Path, project_id: str, seed: int, method: str) -> Path:
    filename = "chaosatlas-full.json" if method == METHODS[0] else "chaosatlas-ablation.json"
    return Path(input_root) / "input_bundles" / project_id / f"seed-{seed}" / filename


def discovery_status(handoff: dict[str, Any], mutations: dict[str, Any]) -> str:
    selected = handoff.get("selected_hypotheses") or []
    generated = mutations.get("generated") or []
    return "valid" if handoff.get("status") == "handoff_ready" and mutations.get("status") == "valid" and len(selected) == 4 and len(generated) == 4 else "method_invalid"


def run_matrix(input_root: Path, profile_path: Path, output: Path, key_path: Path, *, execute: bool, project_id: str = "opentelemetry-demo", model: str = MODEL, base_url: str = BASE_URL) -> dict[str, Any]:
    profile = _load(profile_path)
    if profile.get("runtime_ready") is not True:
        raise ValueError("runtime profile is not ready")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing nonempty discovery output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for seed in SEEDS:
        for method in METHODS:
            bundle_path = bundle_path_for(input_root, project_id, seed, method)
            bundle = _load(bundle_path)
            system, user = build_messages(bundle)
            records.append({"seed": seed, "method_id": method, "bundle_path": str(bundle_path).replace("\\", "/"), "bundle": bundle, "system": system, "user": user, "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(), "request_sha256": hashlib.sha256((system + "\n" + user).encode()).hexdigest()})
    (output / "preflight.json").write_text(json.dumps({"status": "passed", "calls": len(records), "model": model, "base_url": base_url, "human_review": "pending", "knowledge_base_updated": False, "records": [{k: row[k] for k in ("seed", "method_id", "bundle_path", "bundle_sha256", "request_sha256")} for row in records]}, indent=2) + "\n", encoding="utf-8")
    if not execute:
        return {"status": "preflight_passed", "calls": len(records)}

    key = key_path.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError("DeepSeek API key is empty")
    sys.path.insert(0, str(ROOT / "tools"))
    from chaos_eater_adapter.llm_backend import OpenAICompatBackend
    from open_discovery_mutation_compiler import compile_payload
    from run_two_arm_real_project_discovery import build_discovery_handoff

    backend = OpenAICompatBackend(base_url=base_url, api_key=key, model=model, timeout=180, json_mode=True, temperature=0.2, max_output_tokens=4096, disable_thinking=True)
    summary: list[dict[str, Any]] = []
    for record in records:
        run_dir = output / f"seed-{record['seed']}" / record["method_id"].lower()
        run_dir.mkdir(parents=True, exist_ok=False)
        raw = ""
        try:
            raw, metadata = backend.complete(record["system"], record["user"], "")
            payload = _parse_json(raw)
            handoff = build_discovery_handoff(record["bundle"], payload, profile)
            mutations = compile_payload({"status": "valid", "accepted": handoff.get("selected_hypotheses", [])}, record["bundle"]["common_input"]["topology"])
            status = discovery_status(handoff, mutations)
            error = None
        except Exception as exc:
            metadata, payload, handoff, mutations = {}, None, None, None
            status = "transport_failed" if isinstance(exc, (OSError, RuntimeError, TimeoutError)) else "method_invalid"
            error = f"{type(exc).__name__}: {exc}"
        (run_dir / "raw.redacted.txt").write_text(redact_secret(raw, key), encoding="utf-8")
        for name, value in (("payload.json", payload), ("handoff.json", handoff), ("mutations.json", mutations)):
            (run_dir / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        generated = (mutations or {}).get("generated", []) if mutations else []
        if generated:
            mutation_dir = run_dir / "mutations"
            mutation_dir.mkdir()
            for item in generated:
                stem = item["provenance"]["canonical_signature"][:12]
                (mutation_dir / f"{stem}.yaml").write_text(item["yaml"], encoding="utf-8")
                (mutation_dir / f"{stem}.provenance.json").write_text(json.dumps(item["provenance"], indent=2) + "\n", encoding="utf-8")
        result = {"status": status, "error": error, "seed": record["seed"], "method_id": record["method_id"], "model": model, "backend": metadata, "bundle_sha256": record["bundle_sha256"], "request_sha256": record["request_sha256"], "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(), "selected_count": len((handoff or {}).get("selected_hypotheses", [])), "generated_mutations": len(generated), "human_review": "pending", "knowledge_base_updated": False}
        (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        summary.append(result)
    final = {"schema_version": "chaosatlas-two-arm-deepseek-discovery-v1", "status": "completed", "calls": len(summary), "valid": sum(item["status"] == "valid" for item in summary), "method_invalid": sum(item["status"] == "method_invalid" for item in summary), "transport_failed": sum(item["status"] == "transport_failed" for item in summary), "records": summary, "human_review": "pending", "knowledge_base_updated": False, "finished_at": datetime.now(timezone.utc).isoformat()}
    (output / "summary.json").write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--runtime-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--project-id", default="opentelemetry-demo")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = run_matrix(args.input_root, args.runtime_profile, args.output, args.api_key_file, execute=args.execute, project_id=args.project_id)
    print(json.dumps({key: result[key] for key in ("status", "calls")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
