"""r2 prospective blind ranking: Ours-full vs CE-adapter(M1) vs Random.

Frozen BEFORE any execution (pre-registration per codex r2 protocol):
  - pool: prospective_pool_r2.json (18 candidates, all unexecuted)
  - method 1 Ours-full : decision_engine.rank (contract_inventory + SE/DP/JE, no LLM)
  - method 2 CE-adapter: LLM blind selection (ChaosEater-adapter prompt, NO knowledge)
  - method 3 Random    : fixed-seed uniform shuffle

Each method produces a FULL ranking (rank 1..18); budget is Top-8 (uniform
candidate cost). Rankings, per-candidate reason, token counts and timestamps
are persisted to artifacts/experiments/execution/remediation/r2_rankings/.

Honest notes recorded here:
  - r2 pool labels OB-PRODUCTCATALOG-LOSS-100 as contract=explicit_timeout
    (stale label frozen with the pool); decision_engine reads the CURRENT
    contract_inventory where productcatalog is no_timeout (A2 audit) and loss is
    not timeout-protected anyway - the engine's view is used and the label
    discrepancy is logged, not silently resolved.
  - Ours-full's contract knowledge is the current registry; SOCK registrations
    are post-hoc but no SOCK candidates are in this pool, so the post-hoc
    concern does not affect this ranking.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decision_engine import rank as engine_rank  # noqa: E402
from chaos_eater_adapter.llm_backend import OpenAICompatBackend  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = ROOT / "artifacts" / "experiments" / "execution" / "prospective_pool_r2.json"
OUT_DIR = ROOT / "artifacts" / "experiments" / "execution" / "remediation" / "r2_rankings"

SYS_PROMPT = "You are a chaos engineering site reliability engineer."
PROMPT_TEMPLATE = """\
Candidate pool (all UNEXECUTED) from three microservices demos (Online Boutique / OpenTelemetry Demo / Train Ticket):
{pool}

No prior knowledge provided. Rank based on architecture only.
Return the FULL ranking of all {n} candidate IDs as a JSON array, best (most likely to reveal a real weakness) first."""


def load_pool() -> list[dict[str, Any]]:
    doc = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    return doc["candidates"]


def render_prompt(pool: list[dict[str, Any]]) -> str:
    lines = [f"- {c['candidate_id']}: edge={c['edge']} (fault={c['fault']})" for c in pool]
    return PROMPT_TEMPLATE.format(pool="\n".join(lines), n=len(pool))


def parse_ids(text: str) -> list[str]:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError(f"no array in completion: {text[:200]!r}")
    raw = json.loads(text[start : end + 1])
    return [str(x) for x in raw]


def ours_ranking(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [{"candidate_id": c["candidate_id"], "edge": c["edge"]} for c in pool]
    return engine_rank(candidates)


def random_ranking(pool: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    ids = [c["candidate_id"] for c in pool]
    rng = random.Random(seed)
    shuffled = ids[:]
    rng.shuffle(shuffled)
    return [
        {"candidate_id": cid, "rank": i, "score": None, "priority": "random", "reasons": ["uniform random shuffle"]}
        for i, cid in enumerate(shuffled, 1)
    ]


def ce_adapter_ranking(pool: list[dict[str, Any]], api_key: str, base_url: str, model: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    backend = OpenAICompatBackend(base_url=base_url, api_key=api_key, model=model, json_mode=False)
    prompt = render_prompt(pool)
    raw, meta = backend.complete(SYS_PROMPT, prompt, "")
    ids = parse_ids(raw)
    if set(ids) != {c["candidate_id"] for c in pool}:
        raise ValueError(f"LLM ranking missing/extra candidates: {ids}")
    ranked = [{"candidate_id": cid, "rank": i, "score": None, "priority": "ce_adapter", "reasons": []}
              for i, cid in enumerate(ids, 1)]
    return ranked, {"tokens": meta.get("total_tokens"), "raw": raw[:300], "model": model}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--random-seed", type=int, default=202)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")

    pool = load_pool()
    all_ids = [c["candidate_id"] for c in pool]
    frozen_at = datetime.now(timezone.utc).isoformat()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "schema_version": 1,
        "tool": "r2_blind_ranking",
        "frozen_at": frozen_at,
        "frozen_before_execution": True,
        "pool": all_ids,
        "pool_size": len(pool),
        "budget_top_n": 8,
        "notes": [
            "r2 pool labels OB-PRODUCTCATALOG-LOSS-100 contract=explicit_timeout (stale, frozen with pool); "
            "decision_engine uses CURRENT inventory (productcatalog no_timeout, A2 audit); loss not timeout-protected either way.",
            "Ours-full contract knowledge = current registry; no SOCK candidates in this pool so post-hoc SOCK registrations do not affect this ranking.",
        ],
    }

    # Ours-full
    ours = ours_ranking(pool)
    result["ours_full"] = {
        "method": "decision_engine (contract_inventory + SE/DP/JE, no LLM)",
        "ranking": [{"candidate_id": r["candidate_id"], "rank": r["rank"], "score": r["score"],
                     "priority": r["priority"], "reasons": r.get("reasons", [])[:4]} for r in ours],
    }
    print(f"Ours-full top-8: {[r['candidate_id'] for r in ours[:8]]}")

    # CE-adapter (M1, blind LLM)
    ce, meta = ce_adapter_ranking(pool, args.api_key, args.base_url, args.model)
    result["ce_adapter"] = {"method": "ChaosEater-adapter LLM blind (no knowledge)", **meta,
                            "ranking": ce}
    print(f"CE-adapter top-8: {[r['candidate_id'] for r in ce[:8]]}")

    # Random
    rnd = random_ranking(pool, args.random_seed)
    result["random"] = {"method": f"uniform random (seed {args.random_seed})", "ranking": rnd}
    print(f"Random top-8: {[r['candidate_id'] for r in rnd[:8]]}")

    out = args.output_dir / "rankings_frozen.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
