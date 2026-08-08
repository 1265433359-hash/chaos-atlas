"""B3: LLM re-test consistency (temperature variance).

The LLM is stochastic (temperature 0.2); single-call verdict accuracy
(0.65) has unknown variance. This samples 5 candidates x 3 repeated
evidence-mode judgments and reports agreement rate per candidate and
overall, so the M5 numbers carry a consistency bound instead of being a
single lucky draw.

Reads candidate evidence; performs LLM calls only (no injection).
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from chaos_eater_adapter.llm_backend import OpenAICompatBackend
from llm_interpret_evidence import (
    SYS_PROMPT,
    build_candidate_evidence,
    extract_observations,
    load_meta,
    load_run_files,
    parse_completion,
    render_evidence_prompt,
)

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"

# 5 candidates spanning weakness (3/2) and below_threshold (1).
SAMPLE_CANDIDATES = [
    "OB-PAYMENT-LOSS-100",     # weakness 3
    "OB-CHECKOUT-DELAY-2000",  # weakness 3
    "OTEL-EMAIL-DELAY-2000",   # weakness 2
    "TT-STATION-DELAY-2000",   # weakness 2
    "TT-BASIC-DELAY-500",      # below_threshold 1
]


def run_consistency(backend: OpenAICompatBackend, n_repeat: int) -> dict[str, Any]:
    evidence_doc = json.loads((EXECUTION_DIR / "candidate_evidence_status.json").read_text(encoding="utf-8"))
    evidence = build_candidate_evidence(evidence_doc)
    by_id = {c["candidate_id"]: c for c in evidence}
    meta = load_meta()
    by_file = load_run_files()

    per_candidate: dict[str, dict[str, Any]] = {}
    overall_verdicts: list[str] = []
    overall_severity: list[int] = []

    for candidate_id in SAMPLE_CANDIDATES:
        c = by_id.get(candidate_id)
        if not c:
            per_candidate[candidate_id] = {"error": "no evidence"}
            continue
        observations = extract_observations(c["evidence_files"], by_file)
        prompt = render_evidence_prompt(c, meta.get(candidate_id, {}), observations)
        verdicts: list[str] = []
        severities: list[int] = []
        for _ in range(n_repeat):
            raw, _ = backend.complete(SYS_PROMPT, prompt, "")
            judged = parse_completion(raw)
            verdicts.append(str(judged.get("verdict")))
            sev = judged.get("severity")
            severities.append(int(sev) if isinstance(sev, int) else -1)
        per_candidate[candidate_id] = {
            "truth": c["truth"],
            "verdicts": verdicts,
            "severities": severities,
            "verdict_agreement": max(Counter(verdicts).values()) / n_repeat,
            "dominant_verdict": Counter(verdicts).most_common(1)[0][0],
            "verdict_correct": Counter(verdicts).most_common(1)[0][0] == c["truth"],
        }
        overall_verdicts.extend(verdicts)
        overall_severity.extend(severities)

    total = len(overall_verdicts)
    # overall agreement = share of the dominant verdict per candidate.
    per_cand_agreements = [
        r["verdict_agreement"] for r in per_candidate.values() if "verdict_agreement" in r
    ]
    overall_agreement = sum(per_cand_agreements) / len(per_cand_agreements) if per_cand_agreements else 0.0
    correct = sum(1 for r in per_candidate.values() if r.get("verdict_correct"))
    truth_consistent = sum(
        1 for r in per_candidate.values()
        if "verdicts" in r and len(set(r["verdicts"])) == 1
    )

    return {
        "schema_version": 1,
        "tool": "llm_retest_consistency",
        "n_repeat": n_repeat,
        "samples": SAMPLE_CANDIDATES,
        "note": "same evidence prompt repeated n times; agreement bounds the stochastic-LLM variance of M5 verdicts",
        "per_candidate": per_candidate,
        "overall": {
            "mean_per_candidate_agreement": round(overall_agreement, 3),
            "fully_consistent_candidates": truth_consistent,
            "dominant_verdict_correct": correct,
            "candidates_judged": len(per_cand_agreements),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--n-repeat", type=int, default=3)
    parser.add_argument("--output", type=Path, default=EXECUTION_DIR / "llm_retest_consistency.json")
    args = parser.parse_args()
    if args.api_key is None:
        args.api_key = os.environ.get("CHAOS_EATER_API_KEY")
    if not args.api_key:
        raise SystemExit("--api-key or CHAOS_EATER_API_KEY is required")
    backend = OpenAICompatBackend(base_url=args.base_url, api_key=args.api_key, model=args.model, json_mode=False)
    result = run_consistency(backend, args.n_repeat)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "overall": result["overall"]}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
