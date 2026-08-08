"""Generate M1 (ChaosEater-adapter) plans for a deep comparison matrix registry.

Reads an existing registry produced by `generate_deep_comparison_matrix.py`,
replaces the blocked M1 entry with plans ranked by the ChaosEater adapter, and
writes a new registry so the original artifact stays untouched. M2 (FastFI)
remains blocked.

Usage examples:
  python tools/generate_m1_adapter_plans.py --replicate 1 --seed 101
  python tools/generate_m1_adapter_plans.py --replicate 2 --seed 202 \\
      --backend openai-compat --base-url http://localhost:11434/v1 \\
      --api-key "$CHAOS_EATER_API_KEY" --model deepseek-chat
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chaos_eater_adapter.adapter import ChaosEaterAdapter
from chaos_eater_adapter.contexts import build_steady_states, build_user_input
from chaos_eater_adapter.llm_backend import MockBackend, OpenAICompatBackend
from extended_candidate_pool import extended_candidate_pool
from generate_deep_comparison_matrix import CORE_CANDIDATES, make_plan

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"

METHOD_M1 = {
    "id": "M1",
    "name": "ChaosEater-adapter",
    "status": "available",
    "information_tier": ["I0"],
}

CE_INSTRUCTIONS = "Focus on revealing weaknesses such as insufficient recovery functions, resource allocation, and redundancy. Keep every injection scoped to the candidate pool."


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_backend(args: argparse.Namespace, candidates: list[dict[str, Any]] | None = None) -> Any:
    pool = candidates if candidates is not None else CORE_CANDIDATES
    if args.backend == "mock":
        return MockBackend(seed=args.seed, candidates=pool, budget=len(pool))
    if args.backend == "openai-compat":
        if not args.api_key:
            raise SystemExit("--api-key is required for the openai-compat backend")
        return OpenAICompatBackend(
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            json_mode=True,
        )
    raise SystemExit(f"unknown backend: {args.backend}")


def build_i1_context(pool: list[dict[str, Any]]) -> str:
    """I1-tier context: our static graph/local/yaml scores per candidate.

    Score 0 means the candidate is not in our analyzed set (extension of the
    pool). This is exactly the information tier M3/M4 rank on; giving it to the
    LLM measures whether our static analysis improves LLM selection. It must
    NOT include any runtime/execution information (that would be I2 leakage).
    """
    lines = [
        "Candidate scores from our static analysis (graph/local/yaml; "
        "0 = not analyzed in our set):"
    ]
    for c in pool:
        scores = c.get("scores") or {}
        if any(scores.values()):
            lines.append(
                f"- {c['candidate_id']}: graph={scores.get('graph', 0)} "
                f"local={scores.get('local', 0)} yaml={scores.get('yaml', 0)}"
            )
        else:
            lines.append(f"- {c['candidate_id']}: 0 (not in our analyzed set)")
    return "\n".join(lines)


def generate(registry: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    replicate = int(registry.get("replicate"))
    seed = int(registry.get("seed"))
    budget = int(registry.get("candidate_budget") or 10)

    pool = extended_candidate_pool() if getattr(args, "extended", False) else CORE_CANDIDATES
    tier = getattr(args, "tier", "i0")

    m1: dict[str, Any] = {key: value for key, value in METHOD_M1.items()}
    m1["plans"] = []
    m1["provenance"] = {}

    backend = build_backend(args, candidates=pool)
    adapter = ChaosEaterAdapter(backend=backend, candidates=pool, budget=budget)
    extra_context = build_i1_context(pool) if tier == "i1" else None
    result = adapter.select(
        user_input=build_user_input(None, pool),
        steady_states=build_steady_states("all"),
        ce_instructions=CE_INSTRUCTIONS,
        extra_context=extra_context,
    )
    for warning in result.warnings:
        print(f"[m1] warning: {warning}")
    m1["provenance"] = {
        "backend": result.backend_meta.get("backend"),
        "model": result.backend_meta.get("model"),
        "generation_time_ms": result.backend_meta.get("generation_time_ms"),
        "tokens": {
            "prompt": result.backend_meta.get("prompt_tokens"),
            "completion": result.backend_meta.get("completion_tokens"),
            "total": result.backend_meta.get("total_tokens"),
        },
        "event": result.scenario.event,
        "thought": result.scenario.thought,
        "ranked_candidates": [item["candidate_id"] for item in result.ranked_candidates],
        "pool_size": len(pool),
        "tier": tier,
    }
    for rank, ranked in enumerate(result.ranked_candidates, start=1):
        candidate_id = ranked["candidate_id"]
        candidate = next(item for item in pool if item["candidate_id"] == candidate_id)
        plan = make_plan(
            method=METHOD_M1,
            candidate=candidate,
            replicate=replicate,
            rank=rank,
            elapsed_ms=int(result.backend_meta.get("generation_time_ms") or 0),
        )
        if result.backend_meta.get("total_tokens"):
            plan["model_tokens"] = int(result.backend_meta["total_tokens"])
        plan["adapter_note"] = {
            "event": result.scenario.event,
            "backend": result.backend_meta.get("backend"),
            "model": result.backend_meta.get("model"),
        }
        m1["plans"].append(plan)

    methods: list[dict[str, Any]] = []
    for method in registry.get("methods", []):
        if method.get("id") == "M1":
            methods.append(m1)
        else:
            methods.append(method)

    return {
        **registry,
        "tool": "generate_m1_adapter_plans",
        "m1_generated_at": now(),
        "m1_backend": backend.name,
        "methods": methods,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--budget", type=int, default=10, help="candidate budget (pool-wide)")
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="source registry; defaults to deep_matrix_registry_r{replicate}.json",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--backend", choices=["mock", "openai-compat"], default="mock")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--api-key", default=None, help="or set CHAOS_EATER_API_KEY")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument(
        "--extended",
        action="store_true",
        help="use the 20-candidate extended pool (12 core + 8 unexecuted)",
    )
    parser.add_argument(
        "--tier",
        choices=["i0", "i1"],
        default="i0",
        help="i0 = blind LLM (M1); i1 = LLM + our static analysis scores (M5-select)",
    )
    args = parser.parse_args()

    registry_path = args.registry
    if registry_path is None:
        registry_path = (
            EXECUTION_DIR / f"extended_registry_r{args.replicate}.json"
            if args.extended
            else EXECUTION_DIR / f"deep_matrix_registry_r{args.replicate}.json"
        )
    if not registry_path.exists():
        raise SystemExit(f"registry not found: {registry_path}")
    if args.api_key is None:
        args.api_key = __import__("os").environ.get("CHAOS_EATER_API_KEY")

    registry = load_json(registry_path)
    result = generate(registry, args)
    suffix = "m5sel" if args.tier == "i1" else "m1"
    output = args.output or registry_path.with_name(
        f"{registry_path.stem}_{suffix}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    m1 = next(item for item in result["methods"] if item["id"] == "M1")
    prov = m1.get("provenance") or {}
    summary = {
        "output": str(output),
        "replicate": args.replicate,
        "backend": backend_name(result),
        "tier": prov.get("tier"),
        "m1_status": m1["status"],
        "m1_plans": len(m1["plans"]),
        "m1_ranked": prov.get("ranked_candidates"),
        "m1_event": prov.get("event"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


def backend_name(result: dict[str, Any]) -> str:
    return str(result.get("m1_backend") or "unknown")


if __name__ == "__main__":
    raise SystemExit(main())
