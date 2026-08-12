"""Run the authorized P02 open-discovery pilot against DeepSeek.

This runner performs only the method-output phase. It calls the two ChaosAtlas
open arms and the supplementary ChaosEater open adapter, validates every JSON
response, compiles accepted hypotheses, and emits mutation YAML/provenance for
later human-approved execution. It never applies a Kubernetes resource.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "artifacts/experiments/chaosatlas_10_projects"
INPUT = EXP / "open_discovery_bundles/P02/seed-1001"
TOPOLOGY_PATH = EXP / "topology_profiles/P02/topology.json"
RUNTIME_MAP_PATH = EXP / "runtime_profiles/P02/runtime-map.json"
OUT = EXP / "open_discovery_results/P02/seed-1001"
LEDGER = EXP / "cost_token_ledger.json"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
TIMEOUT = 180
RETRIES = 1
SCHEMA_RETRIES = 1
MAX_OUTPUT_TOKENS = 4096

sys.path.insert(0, str(ROOT / "tools"))
from chaos_eater_adapter.llm_backend import OpenAICompatBackend  # noqa: E402
from open_discovery_compiler import contract_from_topology, compile_output  # noqa: E402
from open_discovery_mutation_compiler import compile_payload  # noqa: E402


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_secret(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("DeepSeek key file is empty")
    return value


def extract_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("completion does not contain a JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("completion root must be an object")
    return value


def redact(value: str, secret: str) -> str:
    value = value.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{16,}", r"\1[REDACTED]", value)


def split_prompt(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    marker = "\n===== USER =====\n"
    if marker not in text:
        raise ValueError(f"prompt missing system/user marker: {path}")
    return tuple(text.split(marker, 1))  # type: ignore[return-value]


def compact_prompts(arm: str, common: dict[str, Any], topology: dict[str, Any], knowledge: dict[str, Any] | None) -> tuple[str, str]:
    """Build a short equivalent prompt after the long-prompt pilot hit output truncation."""
    if arm.startswith("ChaosAtlas"):
        system = "Return ONLY a new JSON object; never repeat or quote the input. You are a ChaosAtlas analyst. Propose at most 2 bounded hypotheses from the supplied deployment topology. Use only exact node IDs from topology.nodes in target and call_chain; never use client, external, or prose labels. Do not invent facts, candidate IDs, observations, RCA, shell commands, kubectl commands, or the prompt itself. The root object MUST contain method_id, project_id, project_commit, and hypotheses."
    else:
        system = "Return only one JSON object. You are the ChaosEater FaultScenarioAgent. Propose at most 2 bounded fault hypotheses from the supplied deployment topology. Use only exact node IDs from topology.nodes in target and call_chain; never use client, external, or prose labels. Do not emit shell commands or kubectl commands."
    nodes = [{"id": node.get("id"), "role": node.get("role"), "name": node.get("name")} for node in topology.get("nodes", [])]
    edges = [{"source": edge.get("source"), "target": edge.get("target"), "kind": edge.get("kind")} for edge in topology.get("edges", [])]
    user_obj = {
        "project_id": common["project_id"],
        "project_commit": common["project_commit"],
        "workload": common["workload_summary"],
        "topology": {"graph_hash": topology.get("graph_hash"), "nodes": nodes, "edges": edges},
        "runtime": {"namespace": "chaosatlas-p02", "fault_families": ["pod_kill", "network_delay", "network_loss", "container_cpu_stress"], "bounds": {"delay_ms": [1, 500], "duration_s": [1, 60], "loss_percent": [1, 100], "workers": [1, 2], "load_percent": [1, 80]}},
        "output_schema": {"method_id": "string", "project_id": "string", "project_commit": "40-hex", "hypotheses": [{"hypothesis_id": "H1", "target": "compose/service/api-gateway", "target_kind": "service", "fault_family": "pod_kill", "parameters": {"mode": "one"}, "hypothesis": "string", "weakness_surface": "string", "call_chain": [{"source": "compose/service/api-gateway", "target": "compose/service/config-server", "relation": "depends_on", "evidence_ref": "topology.edges"}], "expected_invariant": "string", "validation_plan": "string", "recovery_expectation": "string"}]},
    }
    if knowledge:
        user_obj["knowledge"] = knowledge.get("facts")
    return system, "Return at most 3 hypotheses. Use exact project_id and project_commit. JSON only:\n" + json.dumps(user_obj, ensure_ascii=True, separators=(",", ":"))


def call(backend: Any, system: str, user: str, call_id: str) -> tuple[str, dict[str, Any], int]:
    last: Exception | None = None
    for attempt in range(1, RETRIES + 2):
        try:
            return (*backend.complete(system, user, ""), attempt)
        except Exception as exc:
            last = exc
            if attempt <= RETRIES:
                time.sleep(2)
    raise RuntimeError(f"{call_id} failed after {RETRIES + 1} attempts: {last}")


def update_ledger(rows: list[dict[str, Any]]) -> None:
    current = load(LEDGER) if LEDGER.exists() else {"schema_version": "1.0", "rows": [], "api_calls": 0, "transport_attempts": 0, "input_tokens": 0, "output_tokens": 0, "billed_tokens": 0, "hard_token_ceiling": 1200000}
    current["api_calls"] = int(current.get("api_calls", 0)) + len(rows)
    current["transport_attempts"] = int(current.get("transport_attempts", 0)) + sum(int(r.get("attempt", 1)) for r in rows)
    for field in ("input_tokens", "output_tokens", "billed_tokens"):
        current[field] = int(current.get(field, 0)) + sum(int(r.get(field, 0) or 0) for r in rows)
    current.setdefault("rows", []).extend(rows)
    current["status"] = "p02_open_discovery_completed"
    LEDGER.write_text(json.dumps(current, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def archive_previous_mutations(out: Path, run_id: str) -> str:
    """Move prior generated mutation files aside before writing a new run.

    The result directory is intentionally stable for consumers, but files from
    an earlier model call must never be mistaken for the current run.  Moving
    them into a timestamped history directory preserves the evidence without
    leaving stale YAML beside the active manifest.
    """
    archive = out / "history" / run_id
    moved = False
    for arm_dir in (out / "chaosatlas-kb-open", out / "chaosatlas-nokb-open", out / "chaoseater-adapter-open"):
        if not arm_dir.exists():
            continue
        stale = [
            path for path in arm_dir.iterdir()
            if path.is_file() and (path.name.startswith("mutation-") or path.name == "mutation_manifest.json")
        ]
        if not stale:
            continue
        destination = archive / arm_dir.name
        destination.mkdir(parents=True, exist_ok=True)
        for path in stale:
            shutil.move(str(path), str(destination / path.name))
        moved = True
    return str(archive.relative_to(ROOT)).replace("\\", "/") if moved else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key-file", type=Path, default=Path(r"C:\APP\project\deepseek_api_key.txt"))
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--compact", action="store_true", help="use the compact prompt after a long-prompt schema failure")
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    common = load(EXP / "input_bundles/P02/seed-1001/common.json")
    topology = load(TOPOLOGY_PATH)
    runtime_map = load(RUNTIME_MAP_PATH)
    contract = contract_from_topology("P02", common["project_commit"], "chaosatlas-p02", "P02-primary-workload", common["workload_summary"]["health"], topology)
    key = parse_secret(args.api_key_file)
    backend = OpenAICompatBackend(base_url=args.base_url, api_key=key, model=MODEL, timeout=TIMEOUT, json_mode=True, temperature=0.2, max_output_tokens=MAX_OUTPUT_TOKENS, disable_thinking=args.compact)
    OUT.mkdir(parents=True, exist_ok=True)
    archived_previous = archive_previous_mutations(OUT, run_id)
    arms = [
        ("ChaosAtlas-KB-open", INPUT / "chaosatlas-kb-open.prompt.txt"),
        ("ChaosAtlas-noKB-open", INPUT / "chaosatlas-nokb-open.prompt.txt"),
        ("ChaosEater-adapter-open", INPUT / "chaoseater-adapter-open.prompt.txt"),
    ]
    results: dict[str, Any] = {"schema_version": "1.0", "project_id": "P02", "seed": 1001, "model": MODEL, "arms": {}, "created_at": datetime.now(timezone.utc).isoformat(), "run_id": run_id, "archived_previous_mutations": archived_previous or None, "mutation_applied": False, "official_chaoseater_status": "environment_blocked_no_native_skaffold"}
    ledger_rows: list[dict[str, Any]] = []
    for arm, prompt_path in arms:
        if args.compact:
            knowledge = load(EXP / "knowledge_cards/P02/knowledge_card.json") if arm == "ChaosAtlas-KB-open" else None
            system, user = compact_prompts(arm, common, topology, knowledge)
        else:
            system, user = split_prompt(prompt_path)
        call_id = f"P02-1001-{arm}"
        arm_dir = OUT / arm.lower()
        arm_dir.mkdir(parents=True, exist_ok=True)
        (arm_dir / "prompt.sha256").write_text(sha256((system + "\n" + user).encode()) + "\n", encoding="utf-8")
        call_records: list[dict[str, Any]] = []
        try:
            raw, meta, attempt = call(backend, system, user, call_id)
            call_records.append({"raw": raw, "meta": meta, "transport_attempt": attempt, "schema_attempt": 1})
        except Exception as exc:
            (arm_dir / "error.txt").write_text(str(exc) + "\n", encoding="utf-8")
            results["arms"][arm] = {"status": "transport_failed", "error": str(exc), "mutation_applied": False}
            ledger_rows.append({"call_id": call_id, "project_id": "P02", "arm": arm, "seed": 1001, "attempt": RETRIES + 1, "transport_status": "transport_failed", "error": str(exc), "timestamp": datetime.now(timezone.utc).isoformat()})
            continue
        try:
            payload = extract_object(raw)
        except Exception as exc:
            schema_error = str(exc)
            if SCHEMA_RETRIES:
                try:
                    retry_raw, retry_meta, retry_attempt = call(backend, system, user, f"{call_id}-schema-retry")
                    call_records.append({"raw": retry_raw, "meta": retry_meta, "transport_attempt": retry_attempt, "schema_attempt": 2})
                    raw, meta, attempt = retry_raw, retry_meta, retry_attempt
                    payload = extract_object(raw)
                    schema_error = ""
                except Exception as retry_exc:
                    schema_error = f"first attempt: {schema_error}; schema retry: {retry_exc}"
            if schema_error:
                (arm_dir / "schema_error.txt").write_text(schema_error + "\n", encoding="utf-8")
                (arm_dir / "raw.redacted.txt").write_text(redact(raw, key), encoding="utf-8")
                response_meta = dict(meta)
                response_meta["attempt"] = attempt
                response_meta["schema_attempts"] = len(call_records)
                (arm_dir / "response_meta.json").write_text(json.dumps(response_meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
                results["arms"][arm] = {"status": "method_invalid", "reason": "response_not_json_object", "error": schema_error, "raw_sha256": sha256(raw.encode()), "backend": meta, "schema_attempts": len(call_records), "mutation_applied": False}
                for record in call_records:
                    record_meta = record["meta"]
                    ledger_rows.append({"call_id": call_id, "project_id": "P02", "arm": arm, "seed": 1001, "attempt": record["transport_attempt"], "schema_attempt": record["schema_attempt"], "input_tokens": record_meta.get("prompt_tokens"), "output_tokens": record_meta.get("completion_tokens"), "billed_tokens": record_meta.get("total_tokens"), "transport_status": "schema_invalid", "timestamp": datetime.now(timezone.utc).isoformat()})
                continue
        (arm_dir / "raw.redacted.txt").write_text(redact(raw, key), encoding="utf-8")
        response_meta = dict(meta)
        response_meta["attempt"] = attempt
        response_meta["schema_attempts"] = len(call_records)
        (arm_dir / "response_meta.json").write_text(json.dumps(response_meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        payload.setdefault("method_id", arm)
        compiled = compile_output(payload, contract)
        mutations = compile_payload(compiled, topology, runtime_map) if compiled.get("status") == "valid" else {"status": "method_invalid", "generated": [], "generated_count": 0, "rejected_count": 1, "rejected": [{"reason": "upstream_compiler_not_valid"}]}
        (arm_dir / "payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (arm_dir / "compiled.json").write_text(json.dumps(compiled, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        for index, entry in enumerate(mutations.get("generated", [])):
            yaml_path = arm_dir / f"mutation-{index + 1}.yaml"
            provenance_path = arm_dir / f"mutation-{index + 1}.provenance.json"
            yaml_path.write_text(entry["yaml"], encoding="utf-8")
            provenance = dict(entry["provenance"])
            provenance.update({"yaml_path": str(yaml_path.relative_to(ROOT)).replace("\\", "/"), "yaml_sha256": sha256(entry["yaml"].encode()), "llm_call_id": call_id, "execution_ready": False})
            provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (arm_dir / "mutation_manifest.json").write_text(json.dumps(mutations, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        results["arms"][arm] = {"prompt_sha256": sha256((system + "\n" + user).encode()), "raw_sha256": sha256(raw.encode()), "backend": meta, "compiled_status": compiled.get("status"), "accepted": compiled.get("accepted_count", 0), "rejected": compiled.get("rejected_count", 0), "generated": mutations.get("generated_count", 0), "mutation_applied": False}
        for record in call_records:
            record_meta = record["meta"]
            ledger_rows.append({"call_id": call_id, "project_id": "P02", "arm": arm, "seed": 1001, "attempt": record["transport_attempt"], "schema_attempt": record["schema_attempt"], "input_tokens": record_meta.get("prompt_tokens"), "output_tokens": record_meta.get("completion_tokens"), "billed_tokens": record_meta.get("total_tokens"), "transport_status": "success" if record["schema_attempt"] == len(call_records) else "schema_invalid", "timestamp": datetime.now(timezone.utc).isoformat()})
    (OUT / "main_result.json").write_text(json.dumps(results, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    update_ledger(ledger_rows)
    print(json.dumps(results, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
