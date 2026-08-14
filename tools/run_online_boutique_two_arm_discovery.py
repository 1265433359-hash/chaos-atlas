"""Run the frozen Online Boutique two-arm discovery matrix and compile mutations."""

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
EXPERIMENT = ROOT / "artifacts/experiments/chaosatlas_two_arm_real_projects_2026-08-13-r4"
INPUT_ROOT = EXPERIMENT / "input_bundles/online-boutique"
PROFILE = EXPERIMENT / "runtime_profiles/online-boutique-r4.json"
DEFAULT_OUTPUT = EXPERIMENT / "runtime_results/online-boutique/formal-r4-discovery"
DEFAULT_KEY = ROOT.parent / "deepseek_api_key.txt"
METHODS = ("ChaosAtlas-full", "ChaosAtlas-ablation")
SEEDS = (1001, 1002, 1003)
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
FORBIDDEN_KEYS = {
    "candidate_id", "candidate_pool", "oracle_label", "prior_selection",
    "runtime_observation", "post_run_rca", "mutation_path", "shell_command",
    "kubectl_command",
}
OUTPUT_SCHEMA = {
    "method_id": "ChaosAtlas-full|ChaosAtlas-ablation",
    "project_id": "online-boutique",
    "project_commit": "40-hex",
    "hypotheses": [{
        "hypothesis_id": "local-id",
        "target": "topology node or source->target edge",
        "target_kind": "service|dependency_edge",
        "fault_family": "pod_kill|network_delay|network_loss|container_cpu_stress",
        "parameters": {},
        "hypothesis": "bounded claim",
        "weakness_surface": "mechanism at risk",
        "call_chain": [{"source": "node", "target": "node", "relation": "edge", "evidence_ref": "topology"}],
        "expected_invariant": "business invariant",
        "validation_plan": "baseline, inject, observe, recover, cleanup, washout",
        "recovery_expectation": "expected recovery",
    }],
    "no_safe_hypothesis_reason": "required only when empty",
}


def canonical_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(data).hexdigest()


def prepare_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"refusing to use nonempty output directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def build_messages(bundle: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are the ChaosAtlas open-discovery analyst. Use only the frozen project "
        "evidence supplied by the user. Return only JSON matching the schema. Do not "
        "invent runtime outcomes, commands, mutation paths, candidate pools, or RCA. "
        "Propose at most eight bounded namespace-local hypotheses in priority order. "
        "Use exact topology node IDs in target and call_chain; do not rewrite IDs as "
        "service/name. Runtime parameters are exact: network_delay uses integer "
        "latency_ms and duration_s; network_loss uses loss_percent and duration_s; "
        "container_cpu_stress uses workers, load_percent, and duration_s; pod_kill "
        "parameters must be exactly {mode: one}."
    )
    user = json.dumps(
        {
            "method_id": bundle.get("method_id"),
            "seed": bundle.get("seed"),
            "common_input": bundle.get("common_input"),
            "knowledge_view": bundle.get("knowledge_view"),
            "output_schema": OUTPUT_SCHEMA,
            "parameter_contract": {
                "network_delay": {"latency_ms": "integer 1..500", "duration_s": "integer 1..60"},
                "network_loss": {"loss_percent": "integer 1..100", "duration_s": "integer 1..60"},
                "container_cpu_stress": {"workers": "integer 1..2", "load_percent": "integer 1..80", "duration_s": "integer 1..60"},
                "pod_kill": {"mode": "one"},
            },
            "target_rule": "Use exact IDs from common_input.topology.nodes and exact source/target IDs from common_input.topology.edges.",
        },
        indent=2,
        ensure_ascii=True,
    )
    return system, user


def _forbidden_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_forbidden_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_paths(child, f"{path}[{index}]"))
    return found


def parse_model_output(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("model output must be an object")
    hits = _forbidden_paths(value)
    if hits:
        raise ValueError(f"forbidden output fields: {hits}")
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) > 8:
        raise ValueError("hypotheses must be a list of at most 8")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()
    profile = load_json(PROFILE)
    if profile.get("runtime_ready") is not True:
        raise RuntimeError("Online Boutique runtime profile is not ready")
    prepare_output_dir(args.output)
    records: list[dict[str, Any]] = []
    for seed in SEEDS:
        for method in METHODS:
            filename = "chaosatlas-full.json" if method == "ChaosAtlas-full" else "chaosatlas-ablation.json"
            bundle_path = INPUT_ROOT / f"seed-{seed}" / filename
            bundle = load_json(bundle_path)
            if (bundle.get("project_id"), bundle.get("seed"), bundle.get("method_id")) != ("online-boutique", seed, method):
                raise ValueError(f"bundle identity mismatch: {bundle_path}")
            system, user = build_messages(bundle)
            records.append({
                "seed": seed,
                "method_id": method,
                "bundle_path": str(bundle_path.relative_to(ROOT)).replace("\\", "/"),
                "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
                "request_sha256": hashlib.sha256((system + "\n" + user).encode()).hexdigest(),
                "bundle": bundle,
                "system": system,
                "user": user,
            })
    (args.output / "preflight.json").write_text(json.dumps({
        "status": "passed", "calls": len(records), "model": args.model,
        "human_review": "pending", "knowledge_base_updated": False,
        "records": [{k: row[k] for k in ("seed", "method_id", "bundle_path", "bundle_sha256", "request_sha256")} for row in records],
    }, indent=2) + "\n", encoding="utf-8")
    if not args.execute:
        print(json.dumps({"status": "preflight_passed", "calls": len(records), "output": str(args.output)}))
        return 0

    key = args.api_key_file.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError("DeepSeek API key file is empty")
    sys.path.insert(0, str(ROOT / "tools"))
    from chaos_eater_adapter.llm_backend import OpenAICompatBackend
    from open_discovery_mutation_compiler import compile_payload
    from run_two_arm_real_project_discovery import build_discovery_handoff

    backend = OpenAICompatBackend(
        base_url=args.base_url, api_key=key, model=args.model, timeout=180,
        json_mode=True, temperature=0.2, max_output_tokens=4096,
        disable_thinking=True,
    )
    summary: list[dict[str, Any]] = []
    for record in records:
        run_dir = args.output / f"seed-{record['seed']}" / record["method_id"].lower()
        run_dir.mkdir(parents=True, exist_ok=False)
        raw = ""
        try:
            raw, metadata = backend.complete(record["system"], record["user"], "")
            payload = parse_model_output(raw)
            handoff = build_discovery_handoff(record["bundle"], payload, profile)
            topology = record["bundle"]["common_input"]["topology"]
            selected = handoff.get("selected_hypotheses", [])
            mutations = compile_payload({"status": "valid", "accepted": selected}, topology)
            status = "valid" if handoff.get("status") == "handoff_ready" and mutations.get("status") == "valid" else "method_invalid"
            error = None
        except Exception as exc:  # fail closed; preserve the remaining matrix
            metadata = {}
            payload = None
            handoff = None
            mutations = None
            status = "transport_failed" if isinstance(exc, RuntimeError) else "method_invalid"
            error = f"{type(exc).__name__}: {exc}"
        redacted = raw.replace(key, "[REDACTED]")
        (run_dir / "raw.redacted.txt").write_text(redacted, encoding="utf-8")
        for name, value in (("payload.json", payload), ("handoff.json", handoff), ("mutations.json", mutations)):
            (run_dir / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        if mutations:
            mutation_dir = run_dir / "mutations"
            mutation_dir.mkdir()
            for item in mutations.get("generated", []):
                name = json.loads(json.dumps(item["provenance"]))["canonical_signature"][:12]
                (mutation_dir / f"{name}.yaml").write_text(item["yaml"], encoding="utf-8")
                (mutation_dir / f"{name}.provenance.json").write_text(json.dumps(item["provenance"], indent=2) + "\n", encoding="utf-8")
        result = {
            "status": status, "error": error, "seed": record["seed"],
            "method_id": record["method_id"], "model": args.model,
            "backend": metadata, "bundle_sha256": record["bundle_sha256"],
            "request_sha256": record["request_sha256"],
            "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "selected_count": len((handoff or {}).get("selected_hypotheses", [])),
            "generated_mutations": int((mutations or {}).get("generated_count", 0)),
            "human_review": "pending", "knowledge_base_updated": False,
        }
        (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        summary.append(result)
    final = {
        "schema_version": "online-boutique-two-arm-discovery-v1",
        "status": "completed", "calls": len(summary),
        "valid": sum(row["status"] == "valid" for row in summary),
        "method_invalid": sum(row["status"] == "method_invalid" for row in summary),
        "transport_failed": sum(row["status"] == "transport_failed" for row in summary),
        "records": summary, "human_review": "pending", "knowledge_base_updated": False,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (args.output / "summary.json").write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: final[k] for k in ("status", "calls", "valid", "method_invalid", "transport_failed")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
