"""Sock Shop three-method comparison: decision_engine vs M1 blind vs M0 random.

Prospective comparison on the Sock Shop candidate pool AFTER the real-chain
verification of orders->payment/shipping 5s Future.get defense.

HONESTY NOTE (2026-08-09 audit, self-circularity fix): this pool compares
THREE methods but the comparison is NOT symmetric in knowledge timing:
  - M1 blind LLM: knowledge was truly frozen BEFORE execution (blind prompt,
    no contract knowledge). Its picks are a genuine blind selection.
  - decision_engine: the contract_inventory entries (SOCK-orders->payment/
    shipping explicit_timeout + loss_bounded) were written to the registry
    AFTER the experiments were run and their results known (backfill). The
    engine's 4/4 is therefore a POST-HOC knowledge-backed result, NOT a
    frozen-before-execution prediction. It demonstrates "once knowledge is
    asset-ized into the registry, the engine deterministically benefits" -
    it does NOT demonstrate "the engine predicts better than blind" under
    equal-timing conditions.
  - M0 random: distribution is timing-free (uniform over the pool).
Consequence: do NOT cite "decision_engine 4/4 vs M1 4/4" as a fair prospective
head-to-head. Cite it as: (a) blind M1 single-sample hit (luck, non-reproducible),
(b) random distribution wastes ~49% budget on protected edges, (c) knowledge-
assetized engine avoids protected edges deterministically (post-hoc).

Pool = 8 Sock Shop edges:
- 4 orders edges (payment/shipping x delay/loss): DEFENDED (5s Future.get)
- 4 front-end edges (carts/catalogue x delay/loss): WEAKNESS (no timeout)

Metrics:
- protected misallocation: budget spent on defended edges (lower is better)
- decision_engine should skip all 4 orders edges (contract hard filter)
- M1 blind has no knowledge hint: may pick key-path orders edges (looks critical)
- M0 random: expected waste = 4/8 = 50% of budget on protected edges

Real-chain execution evidence (frozen, from sock_orders_future_get_verified.md):
- orders->payment: 2s -> 201@4.15s (absorbed), 6s -> 500@5.10s TimeoutException
- orders->shipping: 2s -> 500@5.07s TimeoutException (shipping direct 6s > window)
- front-end->carts/catalogue: loss -> 10s hang, delay -> 2x amplification (no timeout)
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
OUTPUT = ROOT / "artifacts" / "sock-shop" / "sock_three_method_predictions.json"
BUDGET = 4  # top-4 picks

POOL = [
    {"candidate_id": "SOCK-ORDERS-PAYMENT-DELAY-2000", "edge": "orders->payment", "contract": "explicit_timeout"},
    {"candidate_id": "SOCK-ORDERS-PAYMENT-LOSS-100", "edge": "orders->payment", "contract": "explicit_timeout"},
    {"candidate_id": "SOCK-ORDERS-SHIPPING-DELAY-2000", "edge": "orders->shipping", "contract": "explicit_timeout"},
    {"candidate_id": "SOCK-ORDERS-SHIPPING-LOSS-100", "edge": "orders->shipping", "contract": "explicit_timeout"},
    {"candidate_id": "SOCK-FRONTEND-CARTS-DELAY-2000", "edge": "front-end->carts", "contract": "no_timeout"},
    {"candidate_id": "SOCK-FRONTEND-CARTS-LOSS-100", "edge": "front-end->carts", "contract": "no_timeout"},
    {"candidate_id": "SOCK-FRONTEND-CATALOGUE-DELAY-2000", "edge": "front-end->catalogue", "contract": "no_timeout"},
    {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100", "edge": "front-end->catalogue", "contract": "no_timeout"},
]

# Ground truth from real-chain verification (frozen, not given to M1/M0).
GROUND_TRUTH = {
    "SOCK-ORDERS-PAYMENT-DELAY-2000": "defended",
    "SOCK-ORDERS-PAYMENT-LOSS-100": "defended",
    "SOCK-ORDERS-SHIPPING-DELAY-2000": "defended",
    "SOCK-ORDERS-SHIPPING-LOSS-100": "defended",
    "SOCK-FRONTEND-CARTS-DELAY-2000": "weakness",
    "SOCK-FRONTEND-CARTS-LOSS-100": "weakness",
    "SOCK-FRONTEND-CATALOGUE-DELAY-2000": "weakness",
    "SOCK-FRONTEND-CATALOGUE-LOSS-100": "weakness",
}
PROTECTED_IDS = [c["candidate_id"] for c in POOL if c["contract"] == "explicit_timeout"]

SYS_PROMPT = "You are a chaos engineering site reliability engineer."
PROMPT_TEMPLATE = """\
Candidate pool (all UNEXECUTED) from Sock Shop microservices demo (e-commerce: front-end -> orders -> payment/shipping, carts/catalogue):
{pool}

{knowledge_hint}
Return the top-{budget} candidate IDs most likely to reveal a real weakness, as a JSON array.
Only include candidates from the pool. Rank by likelihood of real weakness."""

KNOWLEDGE_HINT = """\
Prior verified knowledge:
- orders->payment and orders->shipping have a 5s per-request timeout (OrdersController Future.get, code-verified): delay is ABSORBED within 5s, and beyond 5s throws TimeoutException (protected, low value).
- front-end->carts and front-end->catalogue have NO timeout: loss hangs the caller 10s, delay amplifies 2x (real weaknesses).
- Loss (100%) on carts/catalogue: always high severity.
Use this to rank: unprotected edges > protected delay."""


def render_prompt(pool: list[dict[str, Any]], knowledge: bool, budget: int) -> str:
    lines = [f"- {c['candidate_id']}: edge={c['edge']} (contract={c['contract']})" for c in pool]
    hint = KNOWLEDGE_HINT if knowledge else "No prior knowledge provided. Rank based on architecture only."
    return PROMPT_TEMPLATE.format(pool="\n".join(lines), knowledge_hint=hint, budget=budget)


def parse_ids(text: str) -> list[str]:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError(f"no array in completion: {text[:150]!r}")
    raw = json.loads(text[start : end + 1])
    return [str(x) for x in raw]


def misallocation(picks: list[str]) -> dict[str, Any]:
    protected = [p for p in picks if p in PROTECTED_IDS]
    found = [p for p in picks if GROUND_TRUTH.get(p) == "weakness"]
    return {
        "picks": picks,
        "n_protected_picked": len(protected),
        "protected_picks": protected,
        "n_weakness_found": len(found),
        "weakness_found": found,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--budget", type=int, default=BUDGET)
    parser.add_argument("--random-seed", type=int, default=202)
    parser.add_argument("--random-trials", type=int, default=100)
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")

    all_ids = [c["candidate_id"] for c in POOL]
    result: dict[str, Any] = {
        "schema_version": 1,
        "tool": "sock_three_method_select",
        "m1_blind_frozen_before_execution": True,
        "decision_engine_knowledge_frozen_before_execution": False,
        "budget": args.budget,
        "pool_size": len(POOL),
        "ground_truth": GROUND_TRUTH,
        "protected_ids": PROTECTED_IDS,
        "note": (
            "Real-chain ground truth frozen from sock_orders_future_get_verified.md "
            "(2026-08-09): orders->payment/shipping defended via 5s Future.get; "
            "front-end->carts/catalogue weak (no timeout). M1 blind gets NO knowledge. "
            "HONESTY (self-circularity audit): contract_inventory SOCK entries were "
            "backfilled AFTER experiments (post-hoc); decision_engine's protected-skip "
            "is knowledge-assetized post-hoc behavior, NOT a frozen-before-execution "
            "prediction. Do not read decision_engine vs M1 as an equal-timing head-to-head."
        ),
    }

    # decision_engine (contract_inventory hard filter, no LLM)
    from decision_engine import contract_hard_filter, selection_hits
    scored: list[tuple[str, float]] = []
    for cid in all_ids:
        cand = {"candidate_id": cid}
        hard = contract_hard_filter(cand)
        if hard:
            continue
        hits = selection_hits(cand)
        score = 10.0 + sum(w for _, w in hits)
        scored.append((cid, score))
    scored.sort(key=lambda x: -x[1])
    de_picks = [cid for cid, _ in scored[: args.budget]]
    result["decision_engine"] = {
        **misallocation(de_picks),
        "source": "contract_hard_filter (SOCK-orders->payment/shipping explicit_timeout) + SE rules (no LLM)",
    }
    print(f"decision_engine: {result['decision_engine']}")

    # M1 blind LLM (no knowledge) + ours-LLM-with-knowledge (control)
    backend = OpenAICompatBackend(base_url=args.base_url, api_key=args.api_key, model=args.model, json_mode=False)
    for label, knowledge in (("m1_blind_llm", False), ("ours_llm_knowledge", True)):
        prompt = render_prompt(POOL, knowledge, args.budget)
        raw, meta = backend.complete(SYS_PROMPT, prompt, "")
        picks = parse_ids(raw)
        result[label] = {**misallocation(picks), "tokens": meta.get("total_tokens"), "raw": raw[:200]}
        print(f"{label}: {result[label]}")

    # M0 random distribution
    rng = random.Random(args.random_seed)
    trials = []
    for _ in range(args.random_trials):
        picks = rng.sample(all_ids, args.budget)
        trials.append({"picks": picks, "n_protected_picked": sum(1 for p in picks if p in PROTECTED_IDS)})
    result["m0_random_distribution"] = {
        "trials": args.random_trials,
        "mean_protected_picked": round(sum(t["n_protected_picked"] for t in trials) / len(trials), 2),
        "expected_protected_ratio": round(len(PROTECTED_IDS) / len(all_ids), 3),
        "sample": trials[:5],
    }
    print(f"m0_random({args.random_trials}): mean protected picked = {result['m0_random_distribution']['mean_protected_picked']}")

    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
