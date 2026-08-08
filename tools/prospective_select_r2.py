"""Prospective head-to-head round 2: our method vs M1, with hard constraints.

Reads a candidate pool from JSON (unexecuted candidates with contract
metadata). HARD CONSTRAINT (not soft hint): candidates whose edge has a
source-verified explicit_timeout AND fault=delay are removed from the pool
BEFORE the LLM sees them — the timeout makes a delay-protected candidate a
wasted pick. Loss faults are NOT protected by timeouts, so they are kept.
The hard constraint is our pipeline's own code; the LLM is unchanged.

M1 (blind) gets the full pool; our method gets the hard-filtered pool + the
knowledge context. Same LLM, same budget — only the knowledge/hard layer
differs.
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
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"

KNOWLEDGE_CONTEXT = """\
Verified contracts (source-level, 2026-08-09):
- OB checkout->productcatalog: 3s timeout (checkoutservice/main.go:161) - delay PROTECTED; loss NOT protected.
- TT basic->station, TT client->station/order: NO timeout (application.yml) - unprotected.
- OTel checkout->payment/email/shipping/product-catalog/currency/cart: NO timeout anywhere
  in checkout (main.go) - all unprotected.
- OB checkout->payment/cart: NO timeout (chargeCard main.go:369) - unprotected.

Verified patterns (20 executed + round-1 prospective):
- A 100% LOSS on ANY synchronous downstream call hangs to the client deadline
  (every loss injected: payment, email, checkout, currency -> 10-12s
  DEADLINE_EXCEEDED or client timeout, severity 3). Loss is the strongest signal.
- A 2000ms DELAY on an unprotected call amplifies or hangs (severity 2-3);
  on a single-call path with no fan-out it propagates 1:1 (below_threshold,
  e.g. TT-BASIC-500/2000, OB-PRODUCTCATALOG with timeout).
- A DELAY on a timeout-protected call is a wasted pick (covered by timeout).

Judgment experience:
- Loss on any edge = highest confidence weakness (severity 3).
- Delay on unprotected edge = likely weakness (severity 2-3).
- Delay on timeout-protected edge = skip (hard-filtered, not even shown).
- Non-critical coupling (email) blocking primary path = high value.

Rank the top-K most likely to reveal a real weakness (severity 2+).
"""

SYS_PROMPT = """\
You are a chaos-engineering weakness predictor. Given candidate fault
injections on microservice edges, rank the top-K most likely to reveal a
real weakness (hang, timeout, error, or material latency amplification).
Answer ONLY with a JSON array of candidate ids, most impactful first:
["CANDIDATE_ID", ...]"""


def load_pool(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc["candidates"]


def hard_filter(pool: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove explicit_timeout+delay candidates (timeout protects delay).
    Returns (kept, filtered)."""
    kept, filtered = [], []
    for c in pool:
        if c.get("contract") == "explicit_timeout" and c.get("fault") == "delay":
            filtered.append(c)
        else:
            kept.append(c)
    return kept, filtered


def render_prompt(pool: list[dict[str, Any]], knowledge: bool) -> str:
    lines = ["Candidate pool (all unexecuted):"]
    for c in pool:
        lines.append(
            f"- {c['candidate_id']}: service={c['app']} edge={c['edge']} "
            f"fault={c['fault']} (contract={c.get('contract','unknown')})"
        )
    if knowledge:
        lines.append("\n" + KNOWLEDGE_CONTEXT)
        lines.append("\nUse the verified knowledge to inform your ranking.")
    else:
        lines.append("\nNo prior knowledge provided. Rank based on architecture only.")
    return "\n".join(lines)


def parse_ids(text: str) -> list[str]:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError(f"no array in completion: {text[:150]!r}")
    return [str(x) for x in json.loads(text[start : end + 1])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, default=EXECUTION_DIR / "prospective_pool_r2.json")
    parser.add_argument("--budget", type=int, default=8)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--output", type=Path, default=EXECUTION_DIR / "prospective_r2_selections.json")
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")

    pool = load_pool(args.pool)
    kept, filtered = hard_filter(pool)
    backend = OpenAICompatBackend(base_url=args.base_url, api_key=args.api_key, model=args.model, json_mode=False)

    result: dict[str, Any] = {
        "schema_version": 1,
        "tool": "prospective_select_r2",
        "pool_size": len(pool),
        "budget": args.budget,
        "hard_filtered": [c["candidate_id"] for c in filtered],
        "hard_filter_reason": "explicit_timeout contract + delay fault = protected (timeout covers delay); loss NOT protected so kept",
    }

    # M1 gets the FULL pool (blind).
    m1_prompt = render_prompt(pool, knowledge=False)
    raw, meta = backend.complete(SYS_PROMPT, m1_prompt, "")
    m1_picks = parse_ids(raw)[: args.budget]
    result["m1_blind_llm"] = {"picks": m1_picks, "tokens": meta.get("total_tokens"), "raw": raw[:200]}
    print(f"m1_blind_llm: {m1_picks}")

    # Our method gets the hard-filtered pool + knowledge.
    ours_prompt = render_prompt(kept, knowledge=True)
    raw2, meta2 = backend.complete(SYS_PROMPT, ours_prompt, "")
    ours_picks = parse_ids(raw2)[: args.budget]
    result["ours_llm_knowledge_hard"] = {"picks": ours_picks, "tokens": meta2.get("total_tokens"), "raw": raw2[:200]}
    print(f"ours_llm_knowledge_hard: {ours_picks}")

    rng = random.Random(202)
    result["m0_random"] = {"picks": rng.sample([c["candidate_id"] for c in pool], args.budget)}

    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
