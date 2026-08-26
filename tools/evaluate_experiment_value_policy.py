"""Replay the information-value policy without cluster or model access."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.experiment_policy import (
    new_policy_state,
    select_next_experiment,
    update_candidate_state,
)
from tools.experiment_policy_schema import POLICY_VERSION
from tools.stop_policy import evaluate_stop


REPLAY_SCHEMA = "chaosatlas-experiment-policy-replay-v1"


def _unwrap_stage_payload(payload: Any, key: str) -> Any:
    """Accept direct payloads and the stage envelope used by pipeline artifacts."""
    current = payload
    while isinstance(current, dict):
        if key in current:
            return current[key]
        nested = current.get("payload")
        if not isinstance(nested, (dict, list)):
            break
        current = nested
    return current


def _candidate_index(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("candidate_id is required")
        if candidate_id in index:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        index[candidate_id] = candidate
    if not index:
        raise ValueError("at least one candidate is required")
    return index


def replay_policy(
    *,
    project_id: str,
    project_commit: str,
    seed: int,
    candidates: list[dict[str, Any]],
    runtime_results: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay recorded runtime outcomes against deterministic policy state.

    The recorded outcome order represents the legacy execution path. The
    policy recommendation is computed before each outcome is ingested, so the
    report can measure decision divergence without pretending the policy was
    actually executed. Runtime classifications are the only state feedback.
    """
    candidate_rows = [deepcopy(item) for item in candidates]
    index = _candidate_index(candidate_rows)
    state = new_policy_state(project_id, project_commit, int(seed), candidate_rows)
    policy_context = dict(context or {})
    decisions: list[dict[str, Any]] = []

    for ordinal, recorded in enumerate(runtime_results, start=1):
        if not isinstance(recorded, dict):
            raise ValueError(f"runtime result {ordinal} must be an object")
        recorded_id = str(recorded.get("candidate_id") or "")
        if recorded_id not in index:
            raise ValueError(f"unknown candidate_id: {recorded_id}")
        before = evaluate_stop(candidate_rows, state["candidate_states"], policy_context)
        selected = before.get("next_candidate_id")
        if selected is None and before.get("stop_reason") is None:
            scored = select_next_experiment(
                candidate_rows,
                state["candidate_states"],
                policy_context,
                budget=1,
            )
            selected = scored.get("candidate_id") if scored else None
        selected_score = next(
            (item for item in before.get("scores", []) if str(item.get("candidate_id")) == str(selected)),
            None,
        )
        decisions.append(
            {
                "ordinal": ordinal,
                "recorded_candidate_id": recorded_id,
                "policy_next_candidate_id": selected,
                "decision_changed": selected is not None and str(selected) != recorded_id,
                "policy_stop_reason_before": before.get("stop_reason"),
                "policy_score": selected_score,
            }
        )
        update_candidate_state(state, dict(recorded))

    after = evaluate_stop(candidate_rows, state["candidate_states"], policy_context)
    stop_reason = after.get("stop_reason") or "replay_exhausted"
    replay_metadata = {
        "cluster_access": False,
        "model_called": False,
        "mutation_executed": False,
    }
    if policy_context:
        replay_metadata["policy_context"] = policy_context
    return {
        "schema_version": REPLAY_SCHEMA,
        "policy_version": POLICY_VERSION,
        "project_id": project_id,
        "project_commit": project_commit,
        "seed": int(seed),
        "input_sha256": state["input_sha256"],
        "recorded_result_count": len(runtime_results),
        "selected_candidate_ids": [
            item["policy_next_candidate_id"]
            for item in decisions
            if item.get("policy_next_candidate_id") is not None
        ],
        "decisions": decisions,
        "candidate_states": state["candidate_states"],
        "stop_record": {
            "stop_reason": stop_reason,
            "policy_stop_reason": after.get("stop_reason"),
            "next_candidate_id": after.get("next_candidate_id"),
            "unresolved_candidate_ids": [
                candidate_id
                for candidate_id, row in state["candidate_states"].items()
                if row.get("status") not in {"blocked", "defended", "weakness", "below_threshold"}
            ],
            "scores": after.get("scores", []),
        },
        "replay_metadata": replay_metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--runtime-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-commit", required=True)
    parser.add_argument("--seed", type=int, default=1001)
    parser.add_argument("--context", type=Path, help="read-only JSON policy context")
    args = parser.parse_args()
    candidates_payload = json.loads(args.candidates.read_text(encoding="utf-8"))
    results_payload = json.loads(args.runtime_results.read_text(encoding="utf-8"))
    candidates = _unwrap_stage_payload(candidates_payload, "candidates")
    runtime_results = _unwrap_stage_payload(results_payload, "runtime_results")
    context = {}
    if args.context:
        context_payload = json.loads(args.context.read_text(encoding="utf-8"))
        if not isinstance(context_payload, dict):
            raise ValueError("policy context must be a JSON object")
        context = context_payload
    report = replay_policy(
        project_id=args.project_id,
        project_commit=args.project_commit,
        seed=args.seed,
        candidates=candidates,
        runtime_results=runtime_results,
        context=context,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(args.output), "stop_reason": report["stop_record"]["stop_reason"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
