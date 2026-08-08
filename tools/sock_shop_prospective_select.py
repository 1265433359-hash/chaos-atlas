"""Sock Shop cross-distribution prospective selection (non-circular).

Freeze the three methods' predictions BEFORE executing any candidate:
- decision_engine (knowledge base, NO LLM): existing decision_ranking_sock.json
- M1 blind LLM (deepseek, NO knowledge): generated here
- M0 random: generated here

All 8 candidates are UNEXECUTED. Predictions are written to
artifacts/sock-shop/sock_shop_predictions.json BEFORE execution, so ground
truth is created after selection for all methods.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any

from chaos_eater_adapter.llm_backend import OpenAICompatBackend

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "sock-shop" / "sock_shop_predictions.json"

# Sock Shop candidates (all unexecuted). Target service + single caller edge.
# HTTPChaos injects on the target service's inbound port 80; each target has
# exactly one caller, so target==edge.
CANDIDATES: list[dict[str, Any]] = [
    {"candidate_id": "SOCK-FRONTEND-CARTS-LOSS-100",       "service": "carts",     "edge": "front-end->carts",     "fault": "abort (loss-like)", "project": "sock-shop"},
    {"candidate_id": "SOCK-FRONTEND-CATALOGUE-LOSS-100",   "service": "catalogue", "edge": "front-end->catalogue", "fault": "abort (loss-like)", "project": "sock-shop"},
    {"candidate_id": "SOCK-ORDERS-PAYMENT-LOSS-100",       "service": "payment",   "edge": "orders->payment",      "fault": "abort (loss-like)", "project": "sock-shop"},
    {"candidate_id": "SOCK-ORDERS-SHIPPING-LOSS-100",      "service": "shipping",  "edge": "orders->shipping",     "fault": "abort (loss-like)", "project": "sock-shop"},
    {"candidate_id": "SOCK-FRONTEND-CARTS-DELAY-2000",     "service": "carts",     "edge": "front-end->carts",     "fault": "delay 2000ms",      "project": "sock-shop"},
    {"candidate_id": "SOCK-FRONTEND-CATALOGUE-DELAY-2000", "service": "catalogue", "edge": "front-end->catalogue", "fault": "delay 2000ms",      "project": "sock-shop"},
    {"candidate_id": "SOCK-ORDERS-PAYMENT-DELAY-2000",     "service": "payment",   "edge": "orders->payment",      "fault": "delay 2000ms",      "project": "sock-shop"},
    {"candidate_id": "SOCK-ORDERS-SHIPPING-DELAY-2000",    "service": "shipping",  "edge": "orders->shipping",     "fault": "delay 2000ms",      "project": "sock-shop"},
]

# M1 blind prompt: NO prior knowledge from our knowledge base. Architecture only.
SYS_PROMPT = "You are a chaos engineering site reliability engineer."


def render_prompt(knowledge: bool) -> str:
    lines = ["Candidate pool (all unexecuted):"]
    for c in CANDIDATES:
        lines.append(
            f"- {c['candidate_id']}: service={c['service']} edge={c['edge']} "
            f"fault={c['fault']} (project={c['project']})"
        )
    if knowledge:
        lines.append("\nUse prior chaos-engineering experience to rank.")
    else:
        lines.append("\nNo prior knowledge provided. Rank based on architecture only.")
    lines.append("\nReturn the top-6 candidate IDs most likely to reveal a real weakness, as a JSON array.")
    return "\n".join(lines)


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
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")

    backend = OpenAICompatBackend(base_url=args.base_url, api_key=args.api_key, model=args.model, json_mode=False)

    result: dict[str, Any] = {
        "schema_version": 1,
        "tool": "sock_shop_prospective_select",
        "frozen_before_execution": True,
        "candidates": [c["candidate_id"] for c in CANDIDATES],
    }

    # decision_engine prediction (knowledge base, no LLM) - load existing ranking
    ranking_path = ROOT / "artifacts" / "sock-shop" / "decision_ranking_sock.json"
    ranking = json.loads(ranking_path.read_text(encoding="utf-8"))
    de_top6 = [r["candidate_id"] for r in ranking["ranking"][:6]]
    result["decision_engine"] = {"picks": de_top6, "source": "decision_ranking_sock.json (no LLM)"}
    print(f"decision_engine: {de_top6}")

    # M1 blind LLM (no knowledge)
    for label, knowledge in (("m1_blind_llm", False),):
        prompt = render_prompt(knowledge)
        raw, meta = backend.complete(SYS_PROMPT, prompt, "")
        picks = parse_ids(raw)
        result[label] = {"picks": picks, "tokens": meta.get("total_tokens"), "raw": raw[:200]}
        print(f"{label}: {picks}")

    # M0 random baseline (seed fixed for reproducibility)
    rng = random.Random(202)
    result["m0_random"] = {"picks": rng.sample([c["candidate_id"] for c in CANDIDATES], 6)}
    print(f"m0_random: {result['m0_random']['picks']}")

    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
