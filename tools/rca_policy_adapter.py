"""Adapt deterministic RCA evidence actions to the experiment-policy contract.

RCA action IDs are intentionally distinct from fault-candidate IDs.  The
adapter shares only value/stop semantics; the RCA state machine remains in
``rca_loop``.
"""

from __future__ import annotations

from typing import Any, Iterable

try:
    from tools.rca_loop import RCA_STATES, plan_next_action
except ModuleNotFoundError:  # direct script invocation
    from rca_loop import RCA_STATES, plan_next_action


def select_rca_action(
    actions: Iterable[dict[str, Any]],
    *,
    rca_status: str,
    discovery_candidate_ids: set[str] | None = None,
    available_preconditions: set[str] | None = None,
) -> dict[str, Any]:
    if rca_status not in RCA_STATES:
        raise ValueError(f"unknown RCA status: {rca_status}")
    candidates = list(actions)
    collision_ids = set(discovery_candidate_ids or set())
    collisions = sorted(str(item.get("action_id")) for item in candidates if str(item.get("action_id")) in collision_ids)
    if collisions:
        candidates = [item for item in candidates if str(item.get("action_id")) not in collision_ids]
        if not candidates:
            raise ValueError(f"RCA/discovery ID collision: {collisions}")
    if rca_status in {"confirmed", "rejected"}:
        return {
            "action_kind": "rca_evidence",
            "selected_action_id": None,
            "stop_reason": "resolved",
            "scores": [],
        }
    plan = plan_next_action(candidates, available_preconditions)
    if plan.get("status") != "planned":
        return {
            "action_kind": "rca_evidence",
            "selected_action_id": None,
            "stop_reason": "blocked",
            "scores": [],
            "rejected": plan.get("rejected", []),
        }
    selected = plan["selected"]
    return {
        "action_kind": "rca_evidence",
        "selected_action_id": str(selected.get("action_id")),
        "stop_reason": None,
        "scores": [selected.get("score", {})],
        "rejected": [{"action_id": item} for item in collisions] if collisions else [],
        "selection_reason": plan.get("selection_reason"),
    }
