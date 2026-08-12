#!/usr/bin/env python3
"""Run the authorized P02 seed-1001 three-arm candidate selection pilot.

This is selection only: it never applies a Chaos Mesh resource.  The three
arms share the frozen candidate pool and ordering.  Only the ChaosAtlas-KB arm
receives the source-only knowledge card; no runtime labels or prior results
are included in any prompt.
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
INPUT_DIR = ROOT / "artifacts/experiments/chaosatlas_10_projects/input_bundles/P02/seed-1001"
POOL_PATH = ROOT / "artifacts/experiments/chaosatlas_10_projects/candidate_pools/P02/candidate_pool.json"
KNOWLEDGE_PATH = ROOT / "artifacts/experiments/chaosatlas_10_projects/knowledge_cards/P02/knowledge_card.json"
OUT_DIR = ROOT / "artifacts/experiments/chaosatlas_10_projects/selection_results/P02/seed-1001"
LEDGER_PATH = ROOT / "artifacts/experiments/chaosatlas_10_projects/cost_token_ledger.json"

sys.path.insert(0, str(ROOT / "tools"))
from chaos_eater_adapter.adapter import ChaosEaterAdapter, extract_json_object  # noqa: E402
from chaos_eater_adapter.contexts import build_steady_states, build_user_input  # noqa: E402
from chaos_eater_adapter.llm_backend import OpenAICompatBackend  # noqa: E402


MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 4096
TIMEOUT_SECONDS = 180
RETRIES = 1
BUDGET = 8
FORBIDDEN = ("oracle_label", "runtime_observation", "post_run_rca", "mutation_path")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n"


class RecordingBackend:
    """Capture raw response text without retaining the request secret."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self.last_raw = ""

    @property
    def name(self) -> str:
        return self.backend.name

    def complete(self, system: str, user: str, format_instructions: str) -> tuple[str, dict[str, Any]]:
        raw, meta = self.backend.complete(system, user, format_instructions)
        self.last_raw = raw
        return raw, meta


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_candidates(pool: list[dict[str, Any]], order: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in pool:
        params = item.get("fault_parameters") or {}
        family = str(item.get("fault_family", ""))
        if family == "network_delay":
            intensity = f"{params.get('latency_ms', '')}ms"
        elif family == "network_loss":
            intensity = f"{params.get('loss_percent', '')}% loss"
        elif family == "container_cpu_stress":
            intensity = f"{params.get('load_percent', '')}% CPU"
        else:
            intensity = "one pod"
        result.append({
            "candidate_id": str(item["candidate_id"]),
            "project_id": str(item.get("project_id", "P02")),
            "service": str(item.get("target", "")),
            "edge": str(item.get("target", "")),
            "fault_family": family,
            "fault_parameters": params,
            "intensity": intensity,
            "duration": str(params.get("duration_s", 0)),
            "invariant": "preserve the gateway HTTP response contract and recover after cleanup",
        })
    by_id = {item["candidate_id"]: item for item in result}
    if set(order) != set(by_id) or len(order) != len(by_id):
        raise ValueError("common candidate_order does not match frozen candidate pool")
    return [by_id[cid] for cid in order]


def validate_no_leakage(text: str) -> None:
    # These fields are prohibited as prompt keys.  The phrase "runtime" in a
    # generic workload contract is fine; only the evidence-bearing keys fail.
    lowered = text.lower()
    hits = [term for term in FORBIDDEN if term.lower() in lowered]
    if hits:
        raise RuntimeError(f"prompt leakage detected: {hits}")


def render_atlas_prompt(common: dict[str, Any], candidates: list[dict[str, Any]], knowledge: dict[str, Any] | None) -> tuple[str, str]:
    system = (
        "You are a senior chaos-engineering analyst. Rank exactly 8 distinct "
        "candidates from the supplied frozen pool by likelihood of exposing a "
        "verifiable reliability weakness. Use only IDs in the pool. Return one "
        "JSON object with selected entries containing candidate_id, rank, and "
        "short rationale. Do not invent observations or results."
    )
    user: dict[str, Any] = {
        "project": {"project_id": common["project_id"], "commit": common["project_commit"]},
        "workload": common["workload_summary"],
        "candidate_pool": candidates,
        "selection_budget_k": BUDGET,
    }
    if knowledge is not None:
        # The card's audit metadata names excluded evidence fields.  That
        # metadata is useful locally but must not become prompt content.
        user["knowledge_supplement"] = {
            key: value for key, value in knowledge.items()
            if key not in {"forbidden_not_present", "unverified"}
        }
    prompt = system + "\n\n===== USER =====\n" + dump(user)
    validate_no_leakage(prompt)
    return system, prompt


def parse_atlas(raw: str, allowed: set[str]) -> list[dict[str, Any]]:
    value = extract_json_object(raw)
    selected = value.get("selected")
    if not isinstance(selected, list):
        raise ValueError("response must contain selected array")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in selected:
        if not isinstance(row, dict):
            raise ValueError("selected entry is not an object")
        cid = str(row.get("candidate_id", "")).strip()
        if cid not in allowed or cid in seen:
            raise ValueError(f"out-of-pool or duplicate candidate: {cid}")
        seen.add(cid)
        out.append({"candidate_id": cid, "rank": len(out) + 1, "rationale": str(row.get("rationale", ""))[:1000]})
    if len(out) != BUDGET:
        raise ValueError(f"expected {BUDGET} candidates, got {len(out)}")
    return out


def parse_secret(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("DeepSeek key file is empty")
    return value


def redact_raw(raw: str, secret: str) -> str:
    value = raw.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(bearer\\s+)[A-Za-z0-9._-]{16,}", r"\\1[REDACTED]", value)


def call_with_retry(backend: Any, system: str, user: str, fmt: str, call_id: str) -> tuple[str, dict[str, Any], int]:
    last: Exception | None = None
    for attempt in range(1, RETRIES + 2):
        try:
            raw, meta = backend.complete(system, user, fmt)
            return raw, meta, attempt
        except Exception as exc:  # backend normalizes transport errors to RuntimeError
            last = exc
            if attempt > RETRIES:
                break
            time.sleep(2)
    raise RuntimeError(f"{call_id} failed after {RETRIES + 1} attempts: {last}")


def update_ledger(rows: list[dict[str, Any]]) -> None:
    current = load(LEDGER_PATH) if LEDGER_PATH.exists() else {"schema_version": "1.0", "api_calls": 0, "transport_attempts": 0, "input_tokens": 0, "output_tokens": 0, "billed_tokens": 0, "hard_token_ceiling": 1200000, "rows": []}
    current["api_calls"] = int(current.get("api_calls", 0)) + len(rows)
    current["transport_attempts"] = int(current.get("transport_attempts", 0)) + sum(int(r.get("attempt", 1)) for r in rows)
    for key in ("input_tokens", "output_tokens", "billed_tokens"):
        current[key] = int(current.get(key, 0)) + sum(int(r.get(key, 0) or 0) for r in rows)
    current.setdefault("rows", []).extend(rows)
    current["status"] = "pilot_p02_seed1001_completed"
    LEDGER_PATH.write_text(dump(current), encoding="utf-8")


def record_failed_arm(results: dict[str, Any], ledger_rows: list[dict[str, Any]], arm: str, call_id: str, exc: Exception, meta: dict[str, Any] | None = None) -> None:
    """Keep one malformed/failed arm from suppressing the other arms."""
    results["arms"][arm] = {
        "status": "schema_invalid" if "JSON" in str(exc) or "json" in str(exc).lower() else "transport_failed",
        "error": str(exc),
        "backend": meta or {},
    }
    ledger_rows.append({
        "call_id": call_id,
        "project_id": "P02",
        "arm": arm,
        "seed": 1001,
        "attempt": 1,
        "input_tokens": (meta or {}).get("prompt_tokens"),
        "output_tokens": (meta or {}).get("completion_tokens"),
        "billed_tokens": (meta or {}).get("total_tokens"),
        "transport_status": results["arms"][arm]["status"],
        "error": str(exc),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key-file", type=Path, default=Path(r"C:\APP\project\deepseek_api_key.txt"))
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    common = load(INPUT_DIR / "common.json")
    pool = normalize_candidates(load(POOL_PATH)["candidates"], common["candidate_order"])
    bundle_hashes = {name: sha256_file(INPUT_DIR / name) for name in ("common.json", "chaosatlas-kb.json", "chaosatlas-nokb.json", "chaoseater-adapter.json")}
    pool_hash = sha256_file(POOL_PATH)
    knowledge = load(KNOWLEDGE_PATH)
    allowed = {row["candidate_id"] for row in pool}
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for arm, k in (("ChaosAtlas-KB", knowledge), ("ChaosAtlas-noKB", None)):
            system, prompt = render_atlas_prompt(common, pool, k)
            print(json.dumps({"arm": arm, "prompt_sha256": sha256_bytes((system + prompt).encode()), "chars": len(system + prompt)}))
        print(json.dumps({"arm": "ChaosEater-adapter", "candidate_count": len(pool), "candidate_pool_sha256": pool_hash}))
        return 0

    key = parse_secret(args.api_key_file)
    backend = RecordingBackend(OpenAICompatBackend(base_url=args.base_url, api_key=key, model=MODEL, timeout=TIMEOUT_SECONDS, json_mode=True, temperature=TEMPERATURE, max_output_tokens=MAX_OUTPUT_TOKENS, disable_thinking=True))
    results: dict[str, Any] = {"schema_version": "1.0", "project_id": "P02", "seed": 1001, "model": MODEL, "temperature": TEMPERATURE, "max_output_tokens": MAX_OUTPUT_TOKENS, "candidate_pool_sha256": pool_hash, "bundle_sha256": bundle_hashes, "created_at": datetime.now(timezone.utc).isoformat(), "arms": {}}
    ledger_rows: list[dict[str, Any]] = []

    for arm, knowledge_view in (("ChaosAtlas-KB", knowledge), ("ChaosAtlas-noKB", None)):
        system, user = render_atlas_prompt(common, pool, knowledge_view)
        call_id = f"P02-1001-{arm}"
        try:
            raw, meta, attempt = call_with_retry(backend, system, user, "", call_id)
            selected = parse_atlas(raw, allowed)
        except Exception as exc:
            record_failed_arm(results, ledger_rows, arm, call_id, exc, locals().get("meta"))
            continue
        prompt_hash = sha256_bytes((system + user).encode("utf-8"))
        (OUT_DIR / f"{arm}.prompt.sha256").write_text(prompt_hash + "\n", encoding="utf-8")
        (OUT_DIR / f"{arm}.raw.redacted.txt").write_text(redact_raw(raw, key), encoding="utf-8")
        results["arms"][arm] = {"selected": selected, "prompt_sha256": prompt_hash, "raw_sha256": sha256_bytes(raw.encode()), "backend": meta}
        ledger_rows.append({"call_id": call_id, "project_id": "P02", "arm": arm, "seed": 1001, "attempt": attempt, "input_tokens": meta.get("prompt_tokens"), "output_tokens": meta.get("completion_tokens"), "billed_tokens": meta.get("total_tokens"), "transport_status": "success", "timestamp": datetime.now(timezone.utc).isoformat()})

    ce_candidates = [{**item, "fault_family": {"pod_kill": "pod_kill", "network_delay": "latency", "network_loss": "packet_loss", "container_cpu_stress": "cpu_stress"}.get(item["fault_family"], item["fault_family"])} for item in pool]
    ce = ChaosEaterAdapter(backend=backend, candidates=ce_candidates, budget=BUDGET)
    try:
        ce_result = ce.select(build_user_input("P02", ce_candidates), build_steady_states("P02"), "Select the most impactful bounded faults from the pool.")
    except Exception as exc:
        record_failed_arm(results, ledger_rows, "ChaosEater-adapter", "P02-1001-ChaosEater-adapter", exc, locals().get("meta"))
        (OUT_DIR / "selection_result.json").write_text(dump(results), encoding="utf-8")
        update_ledger(ledger_rows)
        print(dump({"project_id": "P02", "seed": 1001, "arms": results["arms"], "output": str(OUT_DIR / "selection_result.json")}))
        return 0
    ce_selected = [{"candidate_id": row["candidate_id"], "rank": i + 1} for i, row in enumerate(ce_result.ranked_candidates)]
    if len(ce_selected) != BUDGET:
        raise ValueError(f"ChaosEater-adapter returned {len(ce_selected)} candidates, expected {BUDGET}")
    raw_ce = backend.last_raw
    results["arms"]["ChaosEater-adapter"] = {"selected": ce_selected, "raw_sha256": sha256_bytes(raw_ce.encode()), "backend": ce_result.backend_meta, "warnings": ce_result.warnings}
    (OUT_DIR / "ChaosEater-adapter.raw.redacted.json").write_text(redact_raw(raw_ce, key) + "\n", encoding="utf-8")
    # Adapter uses the same OpenAI call once; its metadata is already captured.
    ledger_rows.append({"call_id": "P02-1001-ChaosEater-adapter", "project_id": "P02", "arm": "ChaosEater-adapter", "seed": 1001, "attempt": 1, "input_tokens": ce_result.backend_meta.get("prompt_tokens"), "output_tokens": ce_result.backend_meta.get("completion_tokens"), "billed_tokens": ce_result.backend_meta.get("total_tokens"), "transport_status": "success", "timestamp": datetime.now(timezone.utc).isoformat()})

    (OUT_DIR / "selection_result.json").write_text(dump(results), encoding="utf-8")
    update_ledger(ledger_rows)
    print(dump({"project_id": "P02", "seed": 1001, "arms": {name: [x["candidate_id"] for x in data["selected"]] for name, data in results["arms"].items()}, "output": str(OUT_DIR / "selection_result.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
