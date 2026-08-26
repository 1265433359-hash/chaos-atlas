"""Bridge bounded discovery handoffs to the deterministic experiment policy."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.causal_identity import canonical_causal_identity, causal_cluster_id
from tools.experiment_policy import score_experiment


MODES = {"legacy", "observe", "shadow", "guarded", "default"}


def _matches(static: dict[str, Any], hypothesis: dict[str, Any]) -> bool:
    return (
        str(static.get("target")) == str(hypothesis.get("target"))
        and str(static.get("target_kind")) == str(hypothesis.get("target_kind"))
        and str(static.get("fault_family")) == str(hypothesis.get("fault_family"))
    )


def _policy_candidates(static_candidates: list[dict[str, Any]], hypotheses: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    candidates: list[dict[str, Any]] = []
    hypothesis_to_candidate: dict[str, str] = {}
    unmatched: list[str] = []
    for hypothesis in hypotheses:
        hypothesis_id = str(hypothesis.get("hypothesis_id") or "")
        match = next((item for item in static_candidates if _matches(item, hypothesis)), None)
        if not match or not hypothesis_id:
            if hypothesis_id:
                unmatched.append(hypothesis_id)
            continue
        candidate = deepcopy(match)
        candidate["hypothesis_id"] = hypothesis_id
        candidate["causal_identity"] = match.get("causal_identity") or canonical_causal_identity(match)
        candidate["causal_cluster_id"] = match.get("causal_cluster_id") or causal_cluster_id(match)
        candidates.append(candidate)
        hypothesis_to_candidate[hypothesis_id] = str(match.get("candidate_id"))
    return candidates, hypothesis_to_candidate, unmatched


def select_handoff_hypotheses(
    static_candidates: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    policy_state: dict[str, Any],
    *,
    mode: str = "legacy",
    budget: int = 1,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unsupported policy mode: {mode}")
    if mode == "legacy":
        return {
            "policy_mode": mode,
            "compiled_hypotheses": deepcopy(hypotheses),
            "policy_selected_hypothesis_ids": [],
            "policy_selected_candidate_ids": [],
            "unmatched_hypothesis_ids": [],
            "stop_reason": None,
            "scores": [],
        }
    candidates, hypothesis_to_candidate, unmatched = _policy_candidates(static_candidates, hypotheses)
    states = policy_state.get("candidate_states") or {}
    context = dict(context or {})
    scores = [score_experiment(item, states.get(str(item.get("candidate_id")), {}), context) for item in candidates]
    scores = [item for item in scores if item["value_per_cost"] != float("-inf")]
    scores.sort(key=lambda item: (-float(item["value_per_cost"]), str(item.get("candidate_id"))))
    selected_scores = scores[: max(0, int(budget))]
    selected_ids = {str(item["candidate_id"]) for item in selected_scores}
    selected_hypothesis_ids = [
        str(item["hypothesis_id"])
        for item in candidates
        if str(item.get("candidate_id")) in selected_ids
    ]
    blocked_only = bool(candidates) and not scores and all(
        item.get("status") == "blocked" or states.get(str(item.get("candidate_id")), {}).get("status") == "blocked"
        for item in candidates
    )
    if unmatched and mode in {"guarded", "default"}:
        stop_reason = "blocked"
    elif not candidates and hypotheses:
        stop_reason = "blocked"
    elif blocked_only:
        stop_reason = "blocked"
    elif not selected_hypothesis_ids and hypotheses:
        stop_reason = "low_expected_value"
    else:
        stop_reason = None
    if mode in {"guarded", "default"} and not unmatched:
        compiled = [item for item in hypotheses if str(item.get("hypothesis_id")) in set(selected_hypothesis_ids)]
    elif mode in {"guarded", "default"}:
        compiled = []
    else:
        compiled = deepcopy(hypotheses)
    return {
        "policy_mode": mode,
        "compiled_hypotheses": compiled,
        "policy_selected_hypothesis_ids": selected_hypothesis_ids,
        "policy_selected_candidate_ids": [hypothesis_to_candidate[item] for item in selected_hypothesis_ids],
        "unmatched_hypothesis_ids": unmatched,
        "stop_reason": stop_reason,
        "scores": selected_scores,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(MODES), required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--hypotheses", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=1)
    args = parser.parse_args()
    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    hypotheses = json.loads(args.hypotheses.read_text(encoding="utf-8"))
    state = json.loads(args.state.read_text(encoding="utf-8"))
    result = select_handoff_hypotheses(candidates.get("candidates", candidates), hypotheses.get("hypotheses", hypotheses), state, mode=args.mode, budget=args.budget)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"policy_mode": args.mode, "selected": result["policy_selected_hypothesis_ids"], "stop_reason": result["stop_reason"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
