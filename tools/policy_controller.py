"""Round-based policy control for the live ChaosAtlas batch runner.

The controller deliberately delegates scoring and stopping to the existing
policy modules.  Its responsibility is lifecycle wiring: freeze a candidate
pool, choose at most one executable candidate per round, and normalize the
child result into a fail-closed feedback record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from tools.feedback_protocol import classify_outcome
from tools.policy_selection_gate import MODES, select_candidates_with_policy
from tools.reproduction_policy import MIN_STABLE_REPRODUCTIONS


DECISION_SCHEMA = "chaosatlas-policy-controller-decision-v1"
FEEDBACK_SCHEMA = "chaosatlas-policy-runtime-feedback-v1"
_WEAKNESS_LABELS = {
    "confirmed_weakness",
    "availability_degraded",
    "functional_degraded",
    "data_integrity_risk",
    "recovery_timeout",
    "no_readiness_false_recovery",
}
_PROTECTED_LABELS = {"protected", "availability_defended"}
_OBSERVATION_LABELS = {"response_observed", "response_preserved"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _artifact_payload(root: Path, filename: str) -> dict[str, Any]:
    document = _read_json(root / filename)
    payload = document.get("payload") if isinstance(document.get("payload"), dict) else document
    return payload if isinstance(payload, dict) else {}


def _artifact_value(root: Path, filename: str, key: str, default: Any = None) -> Any:
    return _artifact_payload(root, filename).get(key, default)


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def normalize_runtime_feedback(result: dict[str, Any], child_root: Path | None = None) -> dict[str, Any]:
    """Project one child run into a deterministic, fail-closed feedback row."""
    normalized = dict(result)
    root = Path(child_root) if child_root is not None else None
    if root is not None:
        for filename, key in (
            ("finding_report.json", "classification"),
            ("rca_report.json", "rca_status"),
            ("knowledge_draft.json", "knowledge_status"),
        ):
            if key not in normalized:
                value = _artifact_value(root, filename, key)
                if value is not None:
                    normalized[key] = value
        finding_payload = _artifact_payload(root, "finding_report.json")
        rca_payload = _artifact_payload(root, "rca_report.json")
        if "attestation" not in normalized:
            attestation = finding_payload.get("attestation") or rca_payload.get("attestation")
            if isinstance(attestation, dict):
                normalized["attestation"] = attestation
        cleanup = _read_json(root / "cleanup_report.json")
        if "cleanup_status" not in normalized and cleanup.get("status") is not None:
            normalized["cleanup_status"] = cleanup.get("status")
        evidence = _read_json(root / "evidence_refs.json")
        if "evidence_refs" not in normalized and evidence.get("records"):
            normalized["evidence_refs"] = evidence.get("records")
        if "evidence_available_count" not in normalized and evidence.get("available_count") is not None:
            normalized["evidence_available_count"] = evidence.get("available_count")

    status = str(normalized.get("status") or "")
    if status == "environment_blocked" or normalized.get("environment_blocked"):
        classification = "environment_blocked"
        eligible = False
        reason = "environment_blocked"
    elif status == "method_invalid" or normalized.get("method_invalid"):
        classification = "method_invalid"
        eligible = False
        reason = "method_invalid"
    elif str(normalized.get("cleanup_status") or "") != "verified":
        classification = "unsupported"
        eligible = False
        reason = "cleanup_not_verified"
    else:
        label = str(normalized.get("policy_classification") or normalized.get("classification") or "")
        if label in _WEAKNESS_LABELS and int(normalized.get("valid_reproductions", 0) or 0) >= MIN_STABLE_REPRODUCTIONS:
            classification = "confirmed_weakness"
        elif label in _PROTECTED_LABELS:
            classification = "protected"
        elif label in _OBSERVATION_LABELS:
            # The business path stayed healthy after a confirmed mutation.
            # This is useful policy evidence, but not a confirmed weakness or
            # a knowledge-promotion claim.
            classification = "latent_risk"
        else:
            classification = classify_outcome(normalized)
        # A complete child must have independent RCA and evidence.  The
        # explicit quality marker is used by offline tests; live children may
        # provide the equivalent evidence_refs artifact.
        evidence_complete = normalized.get("evidence_quality") == "complete" or (
            bool(normalized.get("evidence_refs"))
            and int(normalized.get("evidence_available_count", 1) or 0) > 0
        )
        attestation = normalized.get("attestation")
        lifecycle_complete = (
            isinstance(attestation, dict)
            and attestation.get("valid") is True
            and attestation.get("comparison_eligible") is True
            and all(attestation.get(field) is True for field in (
                "baseline", "injection", "observation", "recovery", "cleanup"
            ))
        )
        oracle_valid = (
            normalized.get("oracle_valid") is True
            or (
                isinstance(attestation, dict)
                and attestation.get("valid") is True
                and attestation.get("independent_oracle") is True
            )
        )
        eligible = (
            status == "live_completed"
            and str(normalized.get("rca_status") or "") in {"bounded", "confirmed"}
            and lifecycle_complete
            and oracle_valid
            and evidence_complete
            and classification in {"confirmed_weakness", "protected", "latent_risk"}
        )
        if eligible:
            reason = "eligible"
        elif status != "live_completed":
            reason = "runtime_not_completed"
        elif str(normalized.get("rca_status") or "") not in {"bounded", "confirmed"}:
            reason = "rca_not_bounded"
        elif label in _WEAKNESS_LABELS and int(normalized.get("valid_reproductions", 0) or 0) < MIN_STABLE_REPRODUCTIONS:
            reason = "reproduction_gate_incomplete"
        elif not lifecycle_complete:
            reason = "lifecycle_incomplete"
        elif not oracle_valid:
            reason = "oracle_not_valid"
        elif not evidence_complete:
            reason = "incomplete_evidence"
        else:
            reason = "classification_not_policy_observable"
        if not eligible:
            classification = classification if classification in {"environment_blocked", "method_invalid"} else "unsupported"

    feedback = dict(normalized)
    feedback.update(
        {
            "schema_version": FEEDBACK_SCHEMA,
            "classification": classification,
            "eligible": bool(eligible),
            "eligibility_reason": reason,
        }
    )
    feedback.setdefault("result_sha256", _sha256({key: value for key, value in feedback.items() if key != "result_sha256"}))
    return feedback


class PolicyController:
    """Adapt the existing selection gate into a one-candidate round API."""

    def __init__(
        self,
        candidates: Iterable[dict[str, Any]],
        policy_state: dict[str, Any],
        *,
        mode: str = "legacy",
        budget: int = 1,
        context: dict[str, Any] | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"unsupported policy mode: {mode}")
        if isinstance(budget, bool) or int(budget) < 1:
            raise ValueError("policy budget must be a positive integer")
        self.candidates = [dict(candidate) for candidate in candidates]
        self.policy_state = policy_state
        self.mode = mode
        self.budget = int(budget)
        self.context = dict(context or {})

    def next_decision(self, *, attempted_candidate_ids: Iterable[str] = ()) -> dict[str, Any]:
        attempted = {str(item) for item in attempted_candidate_ids}
        remaining = [
            candidate
            for candidate in self.candidates
            if str(candidate.get("candidate_id")) not in attempted
        ]
        if not remaining:
            return {
                "schema_version": DECISION_SCHEMA,
                "policy_mode": self.mode,
                "candidate_id": None,
                "execution_candidate_ids": [],
                "policy_selected_candidate_ids": [],
                "stop_reason": "blocked",
                "scores": [],
                "attempted_candidate_ids": sorted(attempted),
                "selection": None,
            }

        selection = select_candidates_with_policy(
            remaining,
            self.policy_state,
            mode=self.mode,
            budget=min(self.budget, len(remaining)),
            legacy_budget=1,
            context=self.context,
        )
        stop_reason = selection.get("stop_reason")
        execution_ids = [str(item) for item in selection.get("execution_candidate_ids") or []]
        if self.mode in {"guarded", "default"} and stop_reason:
            execution_ids = []
        candidate_id = execution_ids[0] if execution_ids else None
        return {
            "schema_version": DECISION_SCHEMA,
            "policy_mode": self.mode,
            "candidate_id": candidate_id,
            "execution_candidate_ids": execution_ids,
            "policy_selected_candidate_ids": list(selection.get("policy_selected_candidate_ids") or []),
            "stop_reason": stop_reason,
            "scores": list(selection.get("scores") or []),
            "attempted_candidate_ids": sorted(attempted),
            "selection": selection,
        }
