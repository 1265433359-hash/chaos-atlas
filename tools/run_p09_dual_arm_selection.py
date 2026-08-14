#!/usr/bin/env python3
"""Run the frozen P09 ChaosAtlas KB/noKB selection experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "artifacts" / "experiments" / "chaosatlas_10_projects"
DEFAULT_KEY_FILE = ROOT.parent / "deepseek_api_key.txt"
DEFAULT_OUTPUT_ROOT = EXP / "selection_results" / "P09"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
SEEDS = (1001, 1002, 1003)
ARMS = (("ChaosAtlas-KB", "chaosatlas-kb.json"), ("ChaosAtlas-noKB", "chaosatlas-nokb.json"))
K = 8
MAX_OUTPUT_TOKENS = 2048
MAX_INPUT_TOKENS_PER_CALL = 8192
TRANSPORT_RETRIES = 1
RUN_TOKEN_CEILING = len(SEEDS) * len(ARMS) * (TRANSPORT_RETRIES + 1) * (
    MAX_INPUT_TOKENS_PER_CALL + MAX_OUTPUT_TOKENS
)
MONETARY_CEILING_CNY = 10.0
FORBIDDEN_PROMPT_TERMS = (
    "oracle_label",
    "runtime_observation",
    "post_run_rca",
    "mutation_path",
    "confirmed_weakness",
)


class BudgetError(RuntimeError):
    pass


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def ensure_budget(
    current_tokens: int, hard_token_ceiling: int, run_token_ceiling: int
) -> None:
    if hard_token_ceiling <= 0 or run_token_ceiling <= 0:
        raise BudgetError("token ceilings must be positive")
    if current_tokens + run_token_ceiling > hard_token_ceiling:
        raise BudgetError("projected P09 run would exceed the global token ceiling")


def prepare_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"refusing to use nonempty output directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _normalize_candidates(pool: list[dict[str, Any]], order: list[str]) -> list[dict[str, Any]]:
    by_id = {str(item.get("candidate_id")): item for item in pool}
    if len(by_id) != len(pool) or len(order) != len(set(order)) or set(order) != set(by_id):
        raise ValueError("candidate_order does not exactly match the frozen P09 pool")
    return [by_id[candidate_id] for candidate_id in order]


def build_records(exp: Path = EXP) -> list[dict[str, Any]]:
    pool_path = exp / "candidate_pools" / "P09" / "candidate_pool.json"
    knowledge_path = exp / "knowledge_cards" / "P09" / "knowledge_card.json"
    pool_doc = load(pool_path)
    pool_hash = sha256_file(pool_path)
    knowledge_hash = sha256_file(knowledge_path)
    knowledge = load(knowledge_path)
    records: list[dict[str, Any]] = []
    for seed in SEEDS:
        seed_dir = exp / "input_bundles" / "P09" / f"seed-{seed}"
        common = load(seed_dir / "common.json")
        if common.get("project_id") != "P09" or common.get("seed") != seed:
            raise ValueError(f"unexpected P09 common input identity for seed {seed}")
        if common.get("candidate_pool_sha256") != pool_hash:
            raise ValueError(f"candidate pool hash mismatch for seed {seed}")
        if int(common.get("candidate_budget_k", 0)) != K:
            raise ValueError(f"selection budget must remain K={K}")
        candidates = _normalize_candidates(pool_doc.get("candidates", []), common["candidate_order"])
        common_canonical = json.dumps(common, sort_keys=True, separators=(",", ":"))
        for arm, filename in ARMS:
            bundle_path = seed_dir / filename
            bundle = load(bundle_path)
            if bundle.get("arm") != arm or bundle.get("common_input") != common:
                raise ValueError(f"paired common input mismatch: {bundle_path}")
            expected_knowledge_hash = knowledge_hash if arm == "ChaosAtlas-KB" else None
            if bundle.get("knowledge_card_sha256") != expected_knowledge_hash:
                raise ValueError(f"knowledge view hash mismatch: {bundle_path}")
            records.append(
                {
                    "project_id": "P09",
                    "arm": arm,
                    "seed": seed,
                    "k": K,
                    "common": common,
                    "common_sha256": sha256_bytes(common_canonical.encode("utf-8")),
                    "bundle_path": bundle_path,
                    "bundle_sha256": sha256_file(bundle_path),
                    "pool_path": pool_path,
                    "pool_sha256": pool_hash,
                    "knowledge": knowledge if arm == "ChaosAtlas-KB" else None,
                    "knowledge_sha256": expected_knowledge_hash,
                    "candidates": candidates,
                }
            )
    return records


def render_prompt(record: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a senior chaos-engineering analyst. Rank exactly 8 distinct candidates "
        "from the supplied frozen pool by likelihood of exposing a verifiable reliability "
        "weakness. Use only candidate IDs from the pool. Return only one JSON object with "
        "a selected array. Each entry must contain candidate_id, rank, and a short rationale. "
        "Do not invent runtime observations, experiment outcomes, or root causes."
    )
    user: dict[str, Any] = {
        "project": {
            "project_id": record["common"]["project_id"],
            "project_commit": record["common"]["project_commit"],
        },
        "deployment_summary": record["common"]["deployment_summary"],
        "workload_summary": record["common"]["workload_summary"],
        "candidate_pool": record["candidates"],
        "selection_budget_k": record["k"],
        "seed": record["seed"],
    }
    if record["knowledge"] is not None:
        user["knowledge_supplement"] = {
            key: value
            for key, value in record["knowledge"].items()
            if key not in {"forbidden_not_present", "unverified"}
        }
    user_text = dump(user)
    lowered = (system + user_text).lower()
    hits = [term for term in FORBIDDEN_PROMPT_TERMS if term in lowered]
    if hits:
        raise ValueError(f"forbidden evidence fields in prompt: {hits}")
    return system, user_text


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("response root must be an object")
    return value


def parse_selection(raw: str, allowed: set[str], k: int) -> list[dict[str, Any]]:
    selected = _extract_json(raw).get("selected")
    if not isinstance(selected, list) or len(selected) != k:
        raise ValueError(f"response must contain exactly {k} selections")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    ranks: list[int] = []
    for item in selected:
        if not isinstance(item, dict):
            raise ValueError("selection entry must be an object")
        candidate_id = str(item.get("candidate_id", ""))
        if candidate_id not in allowed:
            raise ValueError(f"candidate outside frozen pool: {candidate_id}")
        if candidate_id in seen:
            raise ValueError(f"duplicate candidate: {candidate_id}")
        rank = item.get("rank")
        if not isinstance(rank, int):
            raise ValueError("selection rank must be an integer")
        seen.add(candidate_id)
        ranks.append(rank)
        output.append(
            {
                "candidate_id": candidate_id,
                "rank": rank,
                "rationale": str(item.get("rationale", ""))[:1000],
            }
        )
    if sorted(ranks) != list(range(1, k + 1)):
        raise ValueError(f"selection ranks must be exactly 1..{k}")
    return sorted(output, key=lambda item: item["rank"])


def redact(raw: str, secret: str) -> str:
    return re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9._-]{16,}",
        r"\1[REDACTED]",
        raw.replace(secret, "[REDACTED]"),
    )


def read_secret(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("DeepSeek API key file is empty")
    return value


def call_with_retry(backend: Any, system: str, user: str) -> tuple[str, dict[str, Any], int]:
    last_error: Exception | None = None
    for attempt in range(1, TRANSPORT_RETRIES + 2):
        try:
            raw, metadata = backend.complete(system, user, "")
            return raw, metadata, attempt
        except (RuntimeError, TimeoutError) as exc:
            last_error = exc
            if attempt <= TRANSPORT_RETRIES:
                time.sleep(2)
    raise RuntimeError(f"DeepSeek call failed after {TRANSPORT_RETRIES + 1} attempts: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("dual-arm-%Y%m%dT%H%M%SZ"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    records = build_records(EXP)
    ledger_path = EXP / "cost_token_ledger.json"
    ledger = load(ledger_path)
    ensure_budget(
        int(ledger.get("billed_tokens", 0)),
        int(ledger.get("hard_token_ceiling", 0)),
        RUN_TOKEN_CEILING,
    )
    run_dir = args.output_root / args.run_id
    prepare_output_dir(run_dir)
    consent = {
        "schema_version": "1.0",
        "project_id": "P09",
        "arms": [arm for arm, _ in ARMS],
        "seeds": list(SEEDS),
        "planned_successful_calls": len(records),
        "transport_retries_per_call": TRANSPORT_RETRIES,
        "run_token_ceiling": RUN_TOKEN_CEILING,
        "global_token_ceiling": int(ledger["hard_token_ceiling"]),
        "monetary_ceiling_cny": MONETARY_CEILING_CNY,
        "authorized_by_user": True,
        "human_review": "pending",
    }
    (run_dir / "consent.json").write_text(dump(consent), encoding="utf-8")

    preflight_rows = []
    for record in records:
        system, user = render_prompt(record)
        preflight_rows.append(
            {
                "arm": record["arm"],
                "seed": record["seed"],
                "bundle_sha256": record["bundle_sha256"],
                "common_sha256": record["common_sha256"],
                "pool_sha256": record["pool_sha256"],
                "knowledge_sha256": record["knowledge_sha256"],
                "prompt_sha256": sha256_bytes((system + "\n" + user).encode("utf-8")),
                "candidate_count": len(record["candidates"]),
                "selection_budget_k": record["k"],
            }
        )
    (run_dir / "preflight.json").write_text(
        dump({"status": "passed", "records": preflight_rows}), encoding="utf-8"
    )
    if not args.execute:
        print(dump({"status": "preflight_passed", "run_dir": str(run_dir), **consent}))
        return 0

    key = read_secret(args.api_key_file)
    sys.path.insert(0, str(ROOT / "tools"))
    from chaos_eater_adapter.llm_backend import OpenAICompatBackend

    backend = OpenAICompatBackend(
        base_url=args.base_url,
        api_key=key,
        model=MODEL,
        timeout=180,
        json_mode=True,
        temperature=0.2,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        disable_thinking=True,
    )
    results: list[dict[str, Any]] = []
    consecutive_transport_failures = 0
    for record in records:
        system, user = render_prompt(record)
        output = run_dir / f"seed-{record['seed']}" / record["arm"].lower()
        output.mkdir(parents=True, exist_ok=False)
        started = time.perf_counter()
        raw = ""
        metadata: dict[str, Any] = {}
        attempts = 0
        try:
            raw, metadata, attempts = call_with_retry(backend, system, user)
            selected = parse_selection(
                raw, {item["candidate_id"] for item in record["candidates"]}, record["k"]
            )
            status = "valid"
            error = None
            consecutive_transport_failures = 0
        except (RuntimeError, TimeoutError) as exc:
            selected = None
            status = "transport_failed"
            error = str(exc)
            consecutive_transport_failures += 1
        except (ValueError, json.JSONDecodeError) as exc:
            selected = None
            status = "method_invalid"
            error = str(exc)
            consecutive_transport_failures = 0
        result = {
            "schema_version": "1.0",
            "project_id": "P09",
            "arm": record["arm"],
            "seed": record["seed"],
            "status": status,
            "selected": selected,
            "error": error,
            "attempts": attempts,
            "model": MODEL,
            "endpoint": args.base_url,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "backend": metadata,
            "bundle_sha256": record["bundle_sha256"],
            "pool_sha256": record["pool_sha256"],
            "prompt_sha256": sha256_bytes((system + "\n" + user).encode("utf-8")),
            "raw_sha256": sha256_bytes(raw.encode("utf-8")),
            "human_review": "pending",
        }
        (output / "result.json").write_text(dump(result), encoding="utf-8")
        (output / "raw.redacted.txt").write_text(redact(raw, key), encoding="utf-8")
        results.append(result)
        if consecutive_transport_failures >= 3:
            break
    billed = sum(int(row.get("backend", {}).get("total_tokens", 0) or 0) for row in results)
    summary = {
        "schema_version": "1.0",
        "project_id": "P09",
        "status": "completed" if len(results) == len(records) else "stopped_transport_failures",
        "valid": sum(row["status"] == "valid" for row in results),
        "method_invalid": sum(row["status"] == "method_invalid" for row in results),
        "transport_failed": sum(row["status"] == "transport_failed" for row in results),
        "calls_recorded": len(results),
        "billed_tokens": billed,
        "monetary_ceiling_cny": MONETARY_CEILING_CNY,
        "monetary_spend_cny": None,
        "human_review": "pending",
    }
    (run_dir / "summary.json").write_text(dump(summary), encoding="utf-8")
    print(dump({**summary, "run_dir": str(run_dir)}))
    return 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
