"""Mixed-pool prospective comparison: decision_engine vs M1 blind vs M0 random.

Non-circular: predictions frozen BEFORE execution. Pool = OB mixed pool
(protected adservice + unprotected edges). The key differentiator is whether
each method wastes budget on PROTECTED edges:
- decision_engine: contract_hard_filter skips protected delay (adservice)
- M1 blind LLM: no contract knowledge, may pick adservice
- M0 random: uniform, wastes budget on protected ~37.5% of the time

Metrics computed AFTER execution:
- budget efficiency: weaknesses found per budget unit
- protected misallocation: budget spent on defended edges
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chaos_eater_adapter.llm_backend import OpenAICompatBackend

ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = ROOT / "artifacts" / "online-boutique" / "mixed_pool_candidates.json"
OUTPUT = ROOT / "artifacts" / "online-boutique" / "mixed_pool_predictions.json"
BUDGET = 6  # top-6 picks

SYS_PROMPT = "You are a chaos engineering site reliability engineer."
PROMPT_TEMPLATE = """\
Candidate pool (all UNEXECUTED) from Google Online Boutique (Go microservices):
{pool}

{knowledge_hint}
Return the top-{budget} candidate IDs most likely to reveal a real weakness, as a JSON array.
Only include candidates from the pool. Rank by likelihood of real weakness."""

KNOWLEDGE_HINT = """\
Prior verified knowledge:
- frontend->adservice has a 100ms per-request timeout (frontend/rpc.go:120): delay is ABSORBED, low value.
- Other OB edges (checkout->payment/cart/shipping, frontend->currency/productcatalog) have NO timeout: delay hangs the caller.
- Loss (100%) is not covered by any timeout: always high severity.
Use this to rank: unprotected edges and loss > protected delay."""


def load_pool() -> list[dict[str, Any]]:
    doc = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    return doc["candidates"]


def render_prompt(pool: list[dict[str, Any]], knowledge: bool, budget: int) -> str:
    lines = []
    for c in pool:
        lines.append(f"- {c['candidate_id']}: edge={c['edge']} (contract={c['contract']})")
    hint = KNOWLEDGE_HINT if knowledge else "No prior knowledge provided. Rank based on architecture only."
    return PROMPT_TEMPLATE.format(pool="\n".join(lines), knowledge_hint=hint, budget=budget)


def parse_ids(text: str) -> list[str]:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError(f"no array in completion: {text[:150]!r}")
    raw = json.loads(text[start : end + 1])
    return [str(x) for x in raw]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--budget", type=int, default=BUDGET)
    parser.add_argument("--random-seed", type=int, default=202)
    parser.add_argument("--random-trials", type=int, default=100, help="M0 random distribution trials")
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")

    pool = load_pool()
    all_ids = [c["candidate_id"] for c in pool]

    result: dict[str, Any] = {
        "schema_version": 1,
        "tool": "mixed_pool_prospective_select",
        "frozen_before_execution": True,
        "budget": args.budget,
        "pool_size": len(pool),
        "candidates": all_ids,
    }

    # decision_engine (knowledge base, NO LLM)
    from decision_engine import contract_hard_filter, selection_hits
    scored: list[tuple[str, float]] = []
    for cid in all_ids:
        cand = {"candidate_id": cid}
        hard = contract_hard_filter(cand)
        if hard:
            continue  # protected delay: skipped by hard filter
        hits = selection_hits(cand)
        score = 10.0 + sum(w for _, w in hits)
        scored.append((cid, score))
    scored.sort(key=lambda x: -x[1])
    de_picks = [cid for cid, _ in scored[: args.budget]]
    result["decision_engine"] = {"picks": de_picks, "source": "contract_hard_filter + SE rules (no LLM)"}
    print(f"decision_engine: {de_picks}")

    # M1 blind LLM (no knowledge) + our-LLM-with-knowledge (optional control)
    backend = OpenAICompatBackend(base_url=args.base_url, api_key=args.api_key, model=args.model, json_mode=False)
    for label, knowledge in (("m1_blind_llm", False), ("ours_llm_knowledge", True)):
        prompt = render_prompt(pool, knowledge, args.budget)
        raw, meta = backend.complete(SYS_PROMPT, prompt, "")
        picks = parse_ids(raw)
        result[label] = {"picks": picks, "tokens": meta.get("total_tokens"), "raw": raw[:200]}
        print(f"{label}: {picks}")

    # M0 random DISTRIBUTION (not single seed): expected waste on protected edges
    rng = random.Random(args.random_seed)
    protected_ids = [c["candidate_id"] for c in pool if "explicit_timeout" in c["contract"] and "LOSS" not in c["candidate_id"]]
    trials = []
    for _ in range(args.random_trials):
        picks = rng.sample(all_ids, args.budget)
        trials.append({"picks": picks, "n_protected_picked": sum(1 for p in picks if p in protected_ids)})
    result["m0_random_distribution"] = {
        "trials": args.random_trials,
        "mean_protected_picked": round(sum(t["n_protected_picked"] for t in trials) / len(trials), 2),
        "protected_ids": protected_ids,
        "sample": trials[:5],
    }
    print(f"m0_random({args.random_trials} trials): mean protected picked = {result['m0_random_distribution']['mean_protected_picked']}")

    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
