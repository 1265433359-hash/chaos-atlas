#!/usr/bin/env python3
"""Run P09 frozen open-discovery calls and compile outputs without applying faults."""

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
DEFAULT_OUTPUT_ROOT = EXP / "open_discovery_results" / "P09"
OPEN_ARMS = (
    ("ChaosAtlas-KB-open", "chaosatlas-kb-open.json"),
    ("ChaosAtlas-noKB-open", "chaosatlas-nokb-open.json"),
    ("ChaosEater-adapter-open", "chaoseater-adapter-open.json"),
    ("ChaosEater-open", "chaoseater-open.json"),
)
SEEDS = (1001, 1002, 1003)
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
TRANSPORT_RETRIES = 1
MAX_OUTPUT_TOKENS = 4096
MAX_INPUT_TOKENS_PER_CALL = 18000
RUN_TOKEN_CEILING = len(OPEN_ARMS) * len(SEEDS) * (TRANSPORT_RETRIES + 1) * (
    MAX_INPUT_TOKENS_PER_CALL + MAX_OUTPUT_TOKENS
)
MONETARY_CEILING_CNY = 10.0


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


def write_utf8_bytes(path: Path, value: str) -> None:
    path.write_bytes(value.encode("utf-8"))


def prepare_open_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"refusing to use nonempty output directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def ensure_open_budget(current_tokens: int, hard_ceiling: int, run_ceiling: int) -> None:
    if min(hard_ceiling, run_ceiling) <= 0:
        raise BudgetError("token ceilings must be positive")
    if current_tokens + run_ceiling > hard_ceiling:
        raise BudgetError("projected P09 open-discovery run would exceed the global token ceiling")


def prior_p09_tokens(exp: Path) -> int:
    total = 0
    roots = (exp / "open_discovery_results" / "P09", exp / "selection_results" / "P09")
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("result.json"):
            try:
                value = load(path)
                total += int((value.get("backend") or {}).get("total_tokens", 0) or 0)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
    return total


def build_open_records(exp: Path = EXP) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for seed in SEEDS:
        seed_dir = exp / "open_discovery_bundles" / "P09" / f"seed-{seed}"
        for arm, filename in OPEN_ARMS:
            bundle_path = seed_dir / filename
            prompt_path = seed_dir / filename.replace(".json", ".prompt.txt")
            bundle = load(bundle_path)
            common = bundle.get("common_input") or {}
            topology = bundle.get("topology_evidence") or {}
            contract = bundle.get("runtime_contract") or {}
            if bundle.get("arm") != arm or bundle.get("project_id") != "P09" or bundle.get("seed") != seed:
                raise ValueError(f"unexpected P09 open bundle identity: {bundle_path}")
            if bundle.get("protocol") != "protocol_v2_open_discovery.md" or not bundle.get("primary_track"):
                raise ValueError(f"P09 open bundle is not frozen primary track: {bundle_path}")
            if common.get("project_id") != "P09" or contract.get("namespace") != "chaosatlas-p09":
                raise ValueError(f"P09 open contract identity mismatch: {bundle_path}")
            if topology.get("status") != "available" or not topology.get("graph_hash"):
                raise ValueError(f"P09 topology evidence unavailable: {bundle_path}")
            if bundle.get("candidate_pool_visible") or bundle.get("candidate_order_visible"):
                raise ValueError(f"open bundle leaks candidate pool: {bundle_path}")
            records.append(
                {
                    "project_id": "P09",
                    "project_commit": common["project_commit"],
                    "arm": arm,
                    "seed": seed,
                    "bundle_path": bundle_path,
                    "bundle_sha256": sha256_file(bundle_path),
                    "prompt_path": prompt_path,
                    "prompt_sha256": sha256_file(prompt_path),
                    "common": common,
                    "topology": topology,
                    "topology_hash": topology["graph_hash"],
                    "contract": contract,
                    "namespace": contract["namespace"],
                    "max_hypotheses": int(contract.get("max_hypotheses", 0)),
                    "candidate_pool_visible": False,
                }
            )
    return records


def build_prompt(record: dict[str, Any]) -> tuple[str, str]:
    marker = "\n===== USER =====\n"
    frozen = record["prompt_path"].read_text(encoding="utf-8")
    if marker not in frozen:
        raise ValueError(f"frozen prompt marker missing: {record['prompt_path']}")
    system, user = frozen.split(marker, 1)
    return system, user


def parse_open_output(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("open-discovery output root must be an object")
    forbidden = {"candidate_id", "candidate_pool", "oracle_label", "prior_selection", "runtime_observation", "post_run_rca", "mutation_path", "shell_command", "kubectl_command"}
    hits: list[str] = []
    def walk(item: Any, path: str = "$") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in forbidden:
                    hits.append(f"{path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")
    walk(value)
    if hits:
        raise ValueError(f"forbidden output fields: {hits}")
    if value.get("project_id") != "P09":
        raise ValueError("output project_id must be P09")
    if not isinstance(value.get("hypotheses"), list) or len(value["hypotheses"]) > 8:
        raise ValueError("hypotheses must be a list of at most 8")
    if not value["hypotheses"] and not str(value.get("no_safe_hypothesis_reason", "")).strip():
        raise ValueError("empty hypotheses require no_safe_hypothesis_reason")
    return value


def redact(raw: str, secret: str) -> str:
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{16,}", r"\1[REDACTED]", raw.replace(secret, "[REDACTED]"))


def read_secret(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("DeepSeek API key file is empty")
    return value


def call_with_retry(backend: Any, system: str, user: str) -> tuple[str, dict[str, Any], int]:
    last: Exception | None = None
    for attempt in range(1, TRANSPORT_RETRIES + 2):
        try:
            return (*backend.complete(system, user, ""), attempt)
        except (RuntimeError, TimeoutError) as exc:
            last = exc
            if attempt <= TRANSPORT_RETRIES:
                time.sleep(2)
    raise RuntimeError(f"open-discovery call failed after {TRANSPORT_RETRIES + 1} attempts: {last}")


def compile_payload(payload: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "tools"))
    from open_discovery_compiler import RuntimeContract, compile_output
    targets = {str(node.get("id")) for node in record["topology"].get("nodes", []) if node.get("id")}
    contract = RuntimeContract(
        project_id="P09",
        project_commit=record["project_commit"],
        namespace="chaosatlas-p09",
        targets=frozenset(targets | {f"{edge.get('source')}->{edge.get('target')}" for edge in record["topology"].get("edges", [])}),
        workload_id="P09-primary-workload",
        workload_contract=record["common"]["workload_summary"]["health"],
        max_hypotheses=8,
    )
    return compile_output(payload, contract)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("open-%Y%m%dT%H%M%SZ"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    records = build_open_records(EXP)
    ledger = load(EXP / "cost_token_ledger.json")
    prior_tokens = prior_p09_tokens(EXP)
    accounted_tokens = int(ledger.get("billed_tokens", 0)) + prior_tokens
    ensure_open_budget(accounted_tokens, int(ledger.get("hard_token_ceiling", 0)), RUN_TOKEN_CEILING)
    run_dir = args.output_root / args.run_id
    prepare_open_output(run_dir)
    preflight = []
    for record in records:
        system, user = build_prompt(record)
        preflight.append({
            "arm": record["arm"],
            "seed": record["seed"],
            "bundle_sha256": record["bundle_sha256"],
            "topology_hash": record["topology_hash"],
            "prompt_sha256": record["prompt_sha256"],
            "request_sha256": sha256_bytes((system + "\n" + user).encode()),
            "candidate_pool_visible": False,
        })
    (run_dir / "preflight.json").write_text(dump({"status": "passed", "records": preflight}), encoding="utf-8")
    consent = {"project_id": "P09", "calls": len(records), "arms": [arm for arm, _ in OPEN_ARMS], "seeds": list(SEEDS), "transport_retries_per_call": TRANSPORT_RETRIES, "run_token_ceiling": RUN_TOKEN_CEILING, "global_token_ceiling": int(ledger["hard_token_ceiling"]), "central_ledger_tokens_before_run": int(ledger.get("billed_tokens", 0)), "p09_unledgered_tokens_before_run": prior_tokens, "accounted_tokens_before_run": accounted_tokens, "monetary_ceiling_cny": MONETARY_CEILING_CNY, "human_review": "pending"}
    (run_dir / "consent.json").write_text(dump(consent), encoding="utf-8")
    if not args.execute:
        print(dump({"status": "preflight_passed", "run_dir": str(run_dir), **consent}))
        return 0
    key = read_secret(args.api_key_file)
    sys.path.insert(0, str(ROOT / "tools"))
    from chaos_eater_adapter.llm_backend import OpenAICompatBackend
    backend = OpenAICompatBackend(base_url=args.base_url, api_key=key, model=MODEL, timeout=180, json_mode=True, temperature=0.2, max_output_tokens=MAX_OUTPUT_TOKENS, disable_thinking=True)
    results: list[dict[str, Any]] = []
    for record in records:
        system, user = build_prompt(record)
        out = run_dir / f"seed-{record['seed']}" / record["arm"].lower()
        out.mkdir(parents=True, exist_ok=False)
        raw = ""
        meta: dict[str, Any] = {}
        started = time.perf_counter()
        try:
            raw, meta, attempts = call_with_retry(backend, system, user)
            payload = parse_open_output(raw)
            compiled = compile_payload(payload, record)
            status = compiled["status"]
            error = None
        except (RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            attempts = locals().get("attempts", 0)
            payload = None
            compiled = None
            status = "transport_failed" if isinstance(exc, RuntimeError) and not isinstance(exc, ValueError) else "method_invalid"
            error = str(exc)
        result = {"schema_version": "1.0", "project_id": "P09", "arm": record["arm"], "seed": record["seed"], "status": status, "error": error, "attempts": attempts, "compiled": compiled, "bundle_sha256": record["bundle_sha256"], "topology_hash": record["topology_hash"], "prompt_sha256": record["prompt_sha256"], "request_sha256": sha256_bytes((system + "\n" + user).encode()), "raw_sha256": sha256_bytes(raw.encode()), "backend": meta, "human_review": "pending"}
        (out / "result.json").write_text(dump(result), encoding="utf-8")
        (out / "payload.json").write_text(dump(payload) if payload is not None else "null\n", encoding="utf-8")
        (out / "compiled.json").write_text(dump(compiled) if compiled is not None else "null\n", encoding="utf-8")
        write_utf8_bytes(out / "raw.redacted.txt", redact(raw, key))
        results.append(result)
    summary = {"schema_version": "1.0", "project_id": "P09", "calls_recorded": len(results), "valid": sum(row["status"] == "valid" for row in results), "method_invalid": sum(row["status"] == "method_invalid" for row in results), "transport_failed": sum(row["status"] == "transport_failed" for row in results), "human_review": "pending", "auto_apply": False, "monetary_ceiling_cny": MONETARY_CEILING_CNY}
    (run_dir / "summary.json").write_text(dump(summary), encoding="utf-8")
    print(dump({**summary, "run_dir": str(run_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
