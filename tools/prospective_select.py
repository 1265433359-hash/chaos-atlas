"""Prospective head-to-head: our method (LLM + knowledge layer) vs M1 (blind LLM).

Non-circular comparison on 6 UNEXECUTED candidates. Each method picks top-4
BEFORE any execution, so the ground truth is created AFTER selection for both.
The ONLY variable is our knowledge layer (contract inventory + judgment
experience + verified-prior summary); everything else (LLM, candidates,
budget) is identical.

Outcomes will be measured after we execute the union of picks.
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
PROSPECTIVE_DIR = EXECUTION_DIR / "mutations_prospective"

CANDIDATES: list[dict[str, Any]] = [
    {"candidate_id": "OB-FRONTEND-CURRENCY-DELAY-2000", "project": "online-boutique", "service": "currencyservice", "edge": "frontend->currency", "fault": "delay 2000ms", "mutation": "ob-frontend-currency-delay-one.yaml"},
    {"candidate_id": "OB-PRODUCTCATALOG-DELAY-2000", "project": "online-boutique", "service": "productcatalogservice", "edge": "frontend->productcatalog", "fault": "delay 2000ms", "mutation": "ob-productcatalog-delay-2000-one.yaml"},
    {"candidate_id": "OTEL-PRODUCTCATALOG-DELAY-2000", "project": "otel-demo", "service": "product-catalog", "edge": "checkout->product-catalog", "fault": "delay 2000ms", "mutation": "otel-checkout-productcatalog-delay-one.yaml"},
    {"candidate_id": "OTEL-SHIPPING-DELAY-2000", "project": "otel-demo", "service": "shipping", "edge": "checkout->shipping", "fault": "delay 2000ms", "mutation": "otel-checkout-shipping-delay-one.yaml"},
    {"candidate_id": "OTEL-CURRENCY-LOSS-100", "project": "otel-demo", "service": "currency", "edge": "checkout->currency", "fault": "loss 100%", "mutation": "otel-currency-loss-one.yaml"},
    {"candidate_id": "TT-BASIC-DELAY-2000", "project": "train-ticket", "service": "ts-basic-service", "edge": "basic->station", "fault": "delay 2000ms", "mutation": "tt-basic-delay-2000-one.yaml"},
]

# Our knowledge layer (the ONLY difference from M1).
KNOWLEDGE_CONTEXT = """\
Prior knowledge from our verified experiments (I2 evidence, allowed for OUR method):

Verified contracts (source-level):
- OB frontend->productcatalog: checkout calls catalog with a 3s timeout
  (checkoutservice/main.go:161) - catalog is PROTECTED on the checkout path.
- TT basic->station: NO timeout configured (application.yml) - unproteted.

Verified patterns from 20 executed candidates:
- A delay on an unprotected synchronous call amplifies or hangs:
  OB payment/cart/checkout (no timeout) -> 10-12s hang, severity 3.
  TT station/basic/order (no timeout) -> 1:1 to 2x amplification, severity 2.
- A loss (100%) on any synchronous downstream call hangs to the client
  deadline: every loss we injected (payment, email, checkout) -> 10s
  DEADLINE_EXCEEDED, severity 3.
- Product-catalog on OB is protected by a 3s timeout; a 500ms delay on it
  stayed within budget (severity 2 only via amplification, no hang).

Judgment experience (real chaos-engineer rules):
- Coupling: a non-critical dependency blocking the primary path = high value.
- Contract: source-declared timeout present = protection; absent = risk.
- Risk: payment/currency/loss are high-probability real events.

Judge each candidate: is a real weakness likely? Rank top-4 most likely to
reveal a weakness (severity 2+), most impactful first.
"""

SYS_PROMPT = """\
You are a chaos-engineering weakness predictor. Given 6 candidate fault
injections on microservice edges, rank the top-4 most likely to reveal a
real weakness (a hang, timeout, error, or material latency amplification -
severity 2 or 3). Answer ONLY with a JSON array of 4 candidate ids, most
impactful first: ["CANDIDATE_ID", ...]"""


def render_prompt(knowledge: bool) -> str:
    lines = ["Candidate pool (all unexecuted):"]
    for c in CANDIDATES:
        lines.append(
            f"- {c['candidate_id']}: service={c['service']} edge={c['edge']} "
            f"fault={c['fault']} (project={c['project']})"
        )
    if knowledge:
        lines.append("\n" + KNOWLEDGE_CONTEXT)
        lines.append("\nUse the prior knowledge to inform your ranking.")
    else:
        lines.append("\nNo prior knowledge provided. Rank based on architecture only.")
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
    parser.add_argument("--output", type=Path, default=EXECUTION_DIR / "prospective_selections.json")
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")

    backend = OpenAICompatBackend(base_url=args.base_url, api_key=args.api_key, model=args.model, json_mode=False)

    result: dict[str, Any] = {"schema_version": 1, "tool": "prospective_select", "candidates": [c["candidate_id"] for c in CANDIDATES]}
    for label, knowledge in (("ours_llm_knowledge", True), ("m1_blind_llm", False)):
        prompt = render_prompt(knowledge)
        raw, meta = backend.complete(SYS_PROMPT, prompt, "")
        picks = parse_ids(raw)
        result[label] = {"picks": picks, "tokens": meta.get("total_tokens"), "raw": raw[:200]}
        print(f"{label}: {picks}")

    # M0 random baseline: expected by chance on 6 (of which unknown fraction weak).
    rng = random.Random(101)
    result["m0_random"] = {"picks": rng.sample([c["candidate_id"] for c in CANDIDATES], 4)}

    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
