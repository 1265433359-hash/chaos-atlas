"""Run the frozen selection-only LLM ablation.

The command performs a complete preflight before making any API call. It never
deploys, injects faults, or reads the out-of-band oracle. Missing credentials
fail closed. Transport retries, when explicitly requested, reuse the exact same
prompt and seed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INPUT_ROOT = ROOT / "artifacts" / "experiments" / "knowledge_ablation_selection_only"
PROTOCOL = ROOT / "artifacts" / "experiments" / "llm_knowledge_ablation_selection_only_protocol_v1.md"
OUTPUT_ROOT = INPUT_ROOT / "selections"
DEFAULT_API_KEY_FILE = ROOT.parent / "deepseek_api_key.txt"
DEFAULT_RUN_ID = "run-20260810-r2"
PROJECT_ARMS = {"ESHOP": ("blind", "generic", "partial-pre"), "SOCIALNET": ("blind", "generic", "full-pre")}
SEEDS = {"pilot": (1001, 1002, 1003), "formal": (2001, 2002, 2003)}
FORBIDDEN_TERMS = ("mutation_path", "oracle_label", "candidate_protection_classification", "quota_compliance", "environment_blocked", "root_cause")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def input_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for project, arms in PROJECT_ARMS.items():
        for arm_dir in arms:
            for phase, seeds in SEEDS.items():
                bundle_path = INPUT_ROOT / project / arm_dir / phase / "bundle.json"
                bundle = load(bundle_path)
                for seed in seeds:
                    prompt_path = INPUT_ROOT / project / arm_dir / phase / f"seed-{seed}.prompt.txt"
                    records.append({
                        "project": project,
                        "arm_dir": arm_dir,
                        "arm_id": bundle["arm_id"],
                        "phase": phase,
                        "seed": seed,
                        "k": int(bundle["selection_budget_k"]),
                        "bundle": bundle,
                        "bundle_path": bundle_path,
                        "prompt_path": prompt_path,
                    })
    return records


def preflight(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    protocol_sha = sha256_file(PROTOCOL)
    if not records:
        errors.append("no selection records found")
    for record in records:
        prompt = record["prompt_path"].read_text(encoding="utf-8") if record["prompt_path"].exists() else ""
        for term in FORBIDDEN_TERMS:
            if re.search(re.escape(term), prompt):
                errors.append(f"forbidden term {term} in {record['prompt_path']}")
        if not record["prompt_path"].exists():
            errors.append(f"missing prompt: {record['prompt_path']}")
        if not record["bundle_path"].exists():
            errors.append(f"missing bundle: {record['bundle_path']}")
        if record["bundle"].get("protocol_sha256") == protocol_sha:
            errors.append(f"selection-only bundle still points at old protocol: {record['bundle_path']}")
        candidates = record["bundle"]["sections"]["candidate_descriptors"]
        ids = [str(item["candidate_id"]) for item in candidates]
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate candidate ID in {record['bundle_path']}")
        if record["k"] > len(ids):
            errors.append(f"K exceeds pool in {record['bundle_path']}")
    return errors


def parse_selection(raw: str, candidate_ids: set[str], k: int) -> list[dict[str, Any]]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict) or not isinstance(value.get("selected"), list):
        raise ValueError("root must be an object with a selected array")
    selected = value["selected"]
    if len(selected) != k:
        raise ValueError(f"expected exactly {k} selections, got {len(selected)}")
    ids: list[str] = []
    ranks: list[int] = []
    for item in selected:
        if not isinstance(item, dict):
            raise ValueError("selection entry is not an object")
        candidate_id = str(item.get("candidate_id", ""))
        if candidate_id not in candidate_ids:
            raise ValueError(f"candidate not in pool: {candidate_id}")
        if candidate_id in ids:
            raise ValueError(f"duplicate candidate: {candidate_id}")
        rank = item.get("rank")
        if not isinstance(rank, int):
            raise ValueError("rank must be an integer")
        ids.append(candidate_id)
        ranks.append(rank)
    if sorted(ranks) != list(range(1, k + 1)):
        raise ValueError(f"ranks must be exactly 1..{k}, got {ranks}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_API_KEY_FILE)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--transport-retries", type=int, default=0)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    args = parser.parse_args()

    records = input_records()
    errors = preflight(records)
    if errors:
        print(json.dumps({"status": "preflight_failed", "errors": errors}, indent=2), file=sys.stderr)
        return 2
    if args.preflight_only:
        print(json.dumps({"status": "preflight_passed", "records": len(records), "protocol_sha256": sha256_file(PROTOCOL)}, indent=2))
        return 0

    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("CHAOS_EATER_API_KEY")
    if not api_key and args.api_key_file.exists():
        file_lines = args.api_key_file.read_text(encoding="utf-8").splitlines()
        api_key = next((line.strip() for line in file_lines if line.strip() and not line.lstrip().startswith("#")), None)
    if not api_key:
        print(json.dumps({"status": "blocked_missing_api_key", "records": len(records), "message": f"No API key found in environment or {args.api_key_file}."}, indent=2), file=sys.stderr)
        return 3

    sys.path.insert(0, str(ROOT / "tools"))
    from chaos_eater_adapter.llm_backend import OpenAICompatBackend

    backend = OpenAICompatBackend(base_url=args.base_url, api_key=api_key, model=args.model, json_mode=True, temperature=0.2)
    run_root = OUTPUT_ROOT / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    protocol_sha = sha256_file(PROTOCOL)
    ledger_path = run_root / "run_ledger.jsonl"
    for record in records:
        prompt = record["prompt_path"].read_text(encoding="utf-8")
        system, user = prompt.split("===== USER =====", 1)
        prompt_sha = sha256_file(record["prompt_path"])
        bundle_sha = sha256_file(record["bundle_path"])
        candidates = record["bundle"]["sections"]["candidate_descriptors"]
        candidate_ids = {str(item["candidate_id"]) for item in candidates}
        attempts = 0
        status = "transport_failed"
        raw = ""
        metadata: dict[str, Any] = {}
        selected: list[dict[str, Any]] | None = None
        started = time.perf_counter()
        while attempts <= args.transport_retries:
            attempts += 1
            try:
                raw, metadata = backend.complete(system.strip(), user.strip(), "")
                selected = parse_selection(raw, candidate_ids, record["k"])
                status = "valid"
                break
            except (RuntimeError, TimeoutError) as exc:
                metadata = {"error": str(exc)}
                if attempts > args.transport_retries:
                    break
            except (ValueError, json.JSONDecodeError) as exc:
                metadata = {"error": str(exc)}
                status = "parser_invalid"
                break
        result = {
            "schema_version": 1,
            "protocol_sha256": protocol_sha,
            "bundle_sha256": bundle_sha,
            "prompt_sha256": prompt_sha,
            "project": record["project"],
            "arm": record["arm_id"],
            "phase": record["phase"],
            "seed": record["seed"],
            "model": args.model,
            "endpoint": args.base_url,
            "status": status,
            "attempts": attempts,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "metadata": metadata,
            "selected": selected,
        }
        out_dir = run_root / record["project"] / record["arm_dir"] / record["phase"]
        out_dir.mkdir(parents=True, exist_ok=True)
        result_path = out_dir / f"seed-{record['seed']}.json"
        raw_path = out_dir / f"seed-{record['seed']}.raw.txt"
        if result_path.exists() or raw_path.exists():
            raise RuntimeError(f"refusing to overwrite existing result: {result_path}")
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        raw_path.write_text(raw, encoding="utf-8")
        with ledger_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps({k: result[k] for k in ("project", "arm", "phase", "seed", "status", "prompt_sha256", "bundle_sha256")}, ensure_ascii=True) + "\n")
    print(json.dumps({"status": "complete", "records": len(records), "run_id": args.run_id, "output": str(run_root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
