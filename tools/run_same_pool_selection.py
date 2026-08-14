"""Run same-candidate-pool method selection over frozen candidate inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
METHODS = ("ChaosAtlas-full", "ChaosAtlas-ablation", "ChaosEater-adapter")
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
FORBIDDEN_TERMS = (
    "weakness_observed",
    "no_business_impact_observed",
    "runtime_observation",
    "runtime-results",
    "native-full-rca",
    "oracle_label",
    "mutation_path",
)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _display_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(Path(path)).replace("\\", "/")


def _strip_fence(raw: str) -> str:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    return fenced.group(1).strip() if fenced else text


def parse_selection_output(raw: str, *, allowed_ids: set[str], budget: int) -> dict[str, Any]:
    text = _strip_fence(raw)
    lowered = text.lower()
    leaked = [term for term in FORBIDDEN_TERMS if term in lowered]
    if leaked:
        raise ValueError(f"forbidden result fields or labels: {leaked}")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("selection output must be a JSON object")
    selected = value.get("selected_candidates")
    if not isinstance(selected, list):
        raise ValueError("selected_candidates must be a list")
    if len(selected) > budget:
        raise ValueError("selection exceeds budget")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(selected, 1):
        if not isinstance(item, dict):
            raise ValueError("selected candidate must be an object")
        candidate_id = str(item.get("candidate_id") or "")
        if candidate_id not in allowed_ids:
            raise ValueError(f"outside candidate pool: {candidate_id}")
        if candidate_id in seen:
            raise ValueError(f"duplicate candidate: {candidate_id}")
        seen.add(candidate_id)
        normalized.append({
            "candidate_id": candidate_id,
            "rank": int(item.get("rank") or index),
            "reason": str(item.get("reason") or ""),
        })
    return {"selected_candidates": normalized}


def build_messages(method_input: dict[str, Any]) -> tuple[str, str]:
    method = method_input["method_id"]
    system = (
        "You are selecting chaos-engineering candidates from a frozen candidate pool. "
        "Return JSON only. You must select at most the requested budget and every "
        "candidate_id must come verbatim from the supplied pool. Do not invent "
        "new candidates, commands, Kubernetes YAML, runtime observations, old "
        "mutation paths, or outcome labels. Rank by expected ability to expose a "
        "business-impacting weakness under the supplied business oracle."
    )
    if method == "ChaosEater-adapter":
        system += " Use a ChaosEater-style steady-state disruption and experiment-feasibility perspective."
    elif method == "ChaosAtlas-ablation":
        system += " Use only the topology, oracle, and candidate descriptions; no external knowledge."
    else:
        system += " Use the supplied ChaosAtlas generic knowledge view when ranking."
    user = json.dumps(
        {
            "method_id": method,
            "project_id": method_input["project_id"],
            "seed": method_input["seed"],
            "selection_budget": method_input["selection_budget"],
            "business_oracle": sorted({item["business_oracle"] for item in method_input["candidate_pool"]}),
            "knowledge_view": method_input.get("knowledge_view"),
            "candidate_pool_sha256": method_input["candidate_pool_sha256"],
            "candidate_pool": [
                {
                    "candidate_id": item["candidate_id"],
                    "target": item["target"],
                    "fault_family": item["fault_family"],
                    "parameters": item["parameters"],
                    "selector": item["selector"],
                }
                for item in method_input["candidate_pool"]
            ],
            "output_schema": {
                "selected_candidates": [
                    {"candidate_id": "exact id from candidate_pool", "rank": 1, "reason": "brief selection rationale"}
                ]
            },
        },
        indent=2,
        ensure_ascii=True,
    )
    return system, user


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def run_selection(*, freeze_root: Path, output: Path, key_path: Path | None, execute: bool = False, model: str = MODEL, base_url: str = BASE_URL) -> dict[str, Any]:
    freeze_root = Path(freeze_root)
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    manifest = _load(freeze_root / "manifest.json")
    calls: list[dict[str, Any]] = []
    for project_id in manifest["projects"]:
        for seed in manifest["seeds"]:
            for method in METHODS:
                input_path = freeze_root / "method_inputs" / project_id / f"seed-{seed}" / f"{method}.json"
                method_input = _load(input_path)
                allowed = {item["candidate_id"] for item in method_input["candidate_pool"]}
                system, user = build_messages(method_input)
                calls.append({
                    "project_id": project_id,
                    "seed": seed,
                    "method_id": method,
                    "input_path": _display_path(input_path),
                    "request_sha256": hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest(),
                    "candidate_pool_sha256": method_input["candidate_pool_sha256"],
                    "budget": method_input["selection_budget"],
                    "allowed": allowed,
                    "system": system,
                    "user": user,
                })
    preflight = {
        "schema_version": "chaosatlas-same-pool-selection-preflight-v1",
        "status": "passed",
        "freeze_root": str(freeze_root).replace("\\", "/"),
        "calls": len(calls),
        "model": model,
        "execute": execute,
        "human_review": "pending",
        "knowledge_base_updated": False,
        "records": [
            {key: row[key] for key in ("project_id", "seed", "method_id", "input_path", "request_sha256", "candidate_pool_sha256", "budget")}
            for row in calls
        ],
    }
    (output / "preflight.json").write_text(json.dumps(preflight, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    if not execute:
        return {**preflight, "status": "preflight_passed"}
    if key_path is None:
        raise ValueError("key_path is required when execute=True")
    key = Path(key_path).read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError("DeepSeek API key file is empty")
    sys.path.insert(0, str(ROOT / "tools"))
    from chaos_eater_adapter.llm_backend import OpenAICompatBackend

    backend = OpenAICompatBackend(
        base_url=base_url,
        api_key=key,
        model=model,
        timeout=180,
        json_mode=True,
        temperature=0.2,
        max_output_tokens=4096,
        disable_thinking=True,
    )
    summary: list[dict[str, Any]] = []
    for row in calls:
        run_dir = output / row["project_id"] / f"seed-{row['seed']}" / row["method_id"]
        run_dir.mkdir(parents=True, exist_ok=False)
        raw = ""
        try:
            raw, metadata = backend.complete(row["system"], row["user"], "")
            parsed = parse_selection_output(raw, allowed_ids=row["allowed"], budget=int(row["budget"]))
            status = "completed"
            errors: list[str] = []
        except Exception as exc:  # noqa: BLE001 - keep failed call evidence
            metadata = {}
            parsed = {"selected_candidates": []}
            status = "failed"
            errors = [f"{type(exc).__name__}: {exc}"]
        record = {
            "schema_version": "chaosatlas-same-pool-selection-result-v1",
            "project_id": row["project_id"],
            "seed": row["seed"],
            "method_id": row["method_id"],
            "candidate_pool_sha256": row["candidate_pool_sha256"],
            "request_sha256": row["request_sha256"],
            "model": model,
            "model_metadata": metadata,
            "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "selection": parsed,
            "status": status,
            "errors": errors,
            "human_review": "pending",
            "knowledge_base_updated": False,
        }
        (run_dir / "selection.json").write_text(json.dumps(record, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (run_dir / "raw.txt").write_text(raw, encoding="utf-8")
        summary.append({key: record[key] for key in ("project_id", "seed", "method_id", "status", "errors")})
        if status != "completed":
            break
    result = {
        "schema_version": "chaosatlas-same-pool-selection-summary-v1",
        "status": "completed" if len(summary) == len(calls) and all(item["status"] == "completed" for item in summary) else "stopped_on_failure",
        "completed_calls": sum(1 for item in summary if item["status"] == "completed"),
        "total_calls": len(calls),
        "records": summary,
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-path", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = run_selection(freeze_root=args.freeze_root, output=args.output, key_path=args.key_path, execute=args.execute)
    print(json.dumps({key: result[key] for key in ("status",) if key in result}, ensure_ascii=True))
    return 0 if result.get("status") in {"preflight_passed", "completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
