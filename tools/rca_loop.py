"""Small, dependency-free data contract helpers for the automated RCA loop."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from tools.reproduction_policy import MIN_STABLE_REPRODUCTIONS


RCA_STATES = {"pending", "bounded", "confirmed", "rejected"}
CLAIM_LEVELS = {"symptom", "boundary", "mechanism", "source", "rejected"}
KNOWLEDGE_STATES = {
    "none",
    "provisional",
    "local_reusable",
    "cross_project_pending",
    "cross_project_reusable",
    "contested",
}
EVIDENCE_POLARITIES = {"supports", "contradicts", "unavailable", "neutral"}
NON_EVIDENT_OUTCOMES = {
    "environment_blocked",
    "injection_not_confirmed",
    "business_not_reachable",
    "effect_unobserved",
    "recovery_timeout",
    "cleanup_failed",
    "not_run",
}
_WEAKNESS_STATUSES = {
    "candidate",
    "confirmed",
    "protected",
    "unsupported",
    "environment_blocked",
    "rejected",
}
_RCA_TRANSITIONS = {
    "pending": {"pending", "bounded", "confirmed", "rejected"},
    "bounded": {"pending", "bounded", "confirmed", "rejected"},
    "confirmed": {"bounded", "confirmed", "rejected"},
    "rejected": {"rejected", "pending"},
}

_SENSITIVE_FIELD_NAMES = {
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "accesstoken",
    "clientsecret",
    "authorization",
}
_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(?:\"(?P<quoted_key>password|passwd|secret|token|api[_-]?key|access[_-]?token|"
    r"client[_-]?secret|apiKey|authorization)\""
    r"|\b(?P<plain_key>password|passwd|secret|token|api[_-]?key|access[_-]?token|"
    r"client[_-]?secret|apiKey|authorization)\b)"
    r"\s*[:=]\s*(?P<value>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^,};\n]+)"
)
_SAFE_SENSITIVE_PLACEHOLDERS = {
    "explanation",
    "label",
    "unknown",
    "none",
    "null",
    "redacted",
    "redaction",
    "is a field",
    "is documented",
    "is configured",
    "is expected",
    "not set",
    "not configured",
}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _normalise_component(value: Any) -> str:
    text = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def build_weakness_id(project_id: str, edge: str, family: str, operation: str) -> str:
    """Build a stable, human-readable weakness identifier."""

    components = [_normalise_component(value) for value in (project_id, edge, family, operation)]
    return "WS-" + "-".join(component for component in components if component)


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value.strip()


def _canonical_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _is_safe_sensitive_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().strip("\"'").lower() in _SAFE_SENSITIVE_PLACEHOLDERS
    return False


def _sha256_errors(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, str):
        return ["sha256 must be a 64-character hexadecimal string"]
    if _SHA256_RE.fullmatch(value) is None:
        return ["sha256 must be a 64-character hexadecimal string"]
    return []


def _json_contains_sensitive_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _canonical_field_name(key) in _SENSITIVE_FIELD_NAMES:
                if not _is_safe_sensitive_placeholder(item):
                    return True
            if _json_contains_sensitive_value(item):
                return True
    elif isinstance(value, list):
        return any(_json_contains_sensitive_value(item) for item in value)
    return False


def _contains_sensitive_value(text: str) -> bool:
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None
    else:
        if _json_contains_sensitive_value(parsed):
            return True

    for match in _SENSITIVE_FIELD_RE.finditer(text):
        raw_value = match.group("value")
        value = raw_value
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in "\"'":
            value = raw_value[1:-1]
        if not _is_safe_sensitive_placeholder(value):
            return True
    return False


def _raise_if_unsafe_text(name: str, value: str) -> None:
    if _contains_sensitive_value(value):
        raise ValueError(f"sensitive values are not allowed in {name}")


def _normalize_window(window: Any) -> dict[str, str]:
    if window is None:
        return {}
    if not isinstance(window, dict):
        raise ValueError("window must be a dict[str, str]")

    normalized: dict[str, str] = {}
    parsed: dict[str, datetime] = {}
    for key, value in window.items():
        if key not in {"start", "end"}:
            raise ValueError("window keys must be start or end")
        if not isinstance(value, str):
            raise ValueError("window values must be strings")
        if not (value.endswith("Z") or value.endswith("+00:00")):
            raise ValueError("window timestamps must be UTC (Z or +00:00)")
        try:
            parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"window {key} must be valid ISO-8601") from error
        if parsed_value.tzinfo is None or parsed_value.utcoffset() != timedelta(0):
            raise ValueError("window timestamps must be UTC (Z or +00:00)")
        normalized[key] = value
        parsed[key] = parsed_value

    if "start" in parsed and "end" in parsed and parsed["start"] > parsed["end"]:
        raise ValueError("window start must be before or equal to end")
    return dict(normalized)


def make_evidence(
    *,
    evidence_id: str,
    kind: str,
    polarity: str,
    claim_scope: str,
    source_ref: str,
    interpretation: str,
    sha256: str | None = None,
    window: Any = None,
) -> dict[str, Any]:
    """Create one normalized evidence record."""

    evidence_id = _require_text("evidence_id", evidence_id)
    kind = _require_text("kind", kind)
    claim_scope = _require_text("claim_scope", claim_scope)
    source_ref = _require_text("source_ref", source_ref)
    interpretation = _require_text("interpretation", interpretation)
    if not isinstance(polarity, str) or polarity not in EVIDENCE_POLARITIES:
        raise ValueError(f"unknown polarity: {polarity}")
    source_errors = _path_errors(source_ref)
    if source_errors:
        raise ValueError("; ".join(source_errors))
    _raise_if_unsafe_text("interpretation", interpretation)
    sha256_errors = _sha256_errors(sha256)
    if sha256_errors:
        raise ValueError("; ".join(sha256_errors))
    window = _normalize_window(window)

    return {
        "evidence_id": evidence_id,
        "kind": kind,
        "polarity": polarity,
        "claim_scope": claim_scope,
        "source_ref": source_ref.strip().replace("\\", "/"),
        "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "window": window,
        "sha256": sha256,
        "interpretation": interpretation,
    }


def _path_errors(source_ref: Any) -> list[str]:
    if not isinstance(source_ref, str):
        return ["source_ref must not be empty"]
    source_ref = source_ref.strip()
    if not source_ref:
        return ["source_ref must not be empty"]

    errors: list[str] = []
    normalized = source_ref.replace("\\", "/")
    if normalized.startswith("/"):
        errors.append("source_ref must be relative")
    if re.match(r"^[A-Za-z]:", source_ref):
        errors.append("drive paths are not allowed in source_ref")
    elif ":" in source_ref:
        errors.append("URI or colon references are not allowed in source_ref")
    if source_ref.startswith("\\\\") or normalized.startswith("//"):
        errors.append("UNC paths are not allowed in source_ref")
    if any(part == ".." for part in normalized.split("/")):
        errors.append("parent path segments are not allowed in source_ref")
    if "\x00" in source_ref:
        errors.append("NUL bytes are not allowed in source_ref")
    if _contains_sensitive_value(source_ref):
        errors.append("sensitive values are not allowed in source_ref")
    return errors


def validate_evidence_scope(evidence: Mapping[str, Any], claim_scope: str) -> dict[str, Any]:
    """Validate evidence against the claim scope it is allowed to support."""

    errors: list[str] = []
    polarity = evidence.get("polarity")
    if not isinstance(polarity, str) or polarity not in EVIDENCE_POLARITIES:
        errors.append(f"unknown polarity: {polarity}")
    if evidence.get("claim_scope") != claim_scope:
        errors.append("claim_scope does not match")
    errors.extend(_path_errors(evidence.get("source_ref")))
    errors.extend(_sha256_errors(evidence.get("sha256")))
    try:
        _normalize_window(evidence.get("window"))
    except ValueError as error:
        errors.append(str(error))

    interpretation = evidence.get("interpretation")
    if not isinstance(interpretation, str) or not interpretation.strip():
        errors.append("interpretation must not be empty")
    elif _contains_sensitive_value(interpretation):
        errors.append("sensitive values are not allowed in interpretation")

    return {"valid": not errors, "errors": errors}


def evidence_polarity_counts(evidence_list: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {polarity: 0 for polarity in EVIDENCE_POLARITIES}
    for evidence in evidence_list:
        polarity = evidence.get("polarity")
        if polarity in counts:
            counts[polarity] += 1
    return {polarity: counts[polarity] for polarity in ("supports", "contradicts", "unavailable", "neutral")}


def claim_level_for_status(status: str, mechanism_level: str | None = None) -> str:
    """Map RCA state to the strongest claim level the state permits."""

    if status == "rejected":
        return "rejected"
    if status == "confirmed":
        return "source" if mechanism_level == "source" else "mechanism"
    if status == "bounded":
        return "boundary"
    return "symptom"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def evaluate_rca_transition(
    *,
    current: str,
    target: str,
    boundary_confirmed: bool,
    supporting_evidence: int,
    required_evidence_complete: bool,
    discriminating_action: bool,
    high_severity_contradiction: bool,
) -> dict[str, Any]:
    """Evaluate one auditable RCA state transition without mutating a case."""

    if current not in RCA_STATES or target not in RCA_STATES:
        return {"allowed": False, "reason": "unknown_rca_state"}
    if target not in _RCA_TRANSITIONS[current]:
        return {"allowed": False, "reason": "illegal_rca_transition"}
    if current == target:
        return {"allowed": True, "next_status": target, "reason": "state_unchanged"}

    if target == "bounded":
        if not boundary_confirmed or supporting_evidence < 1:
            return {"allowed": False, "reason": "bounded_requires_boundary_and_support"}
        return {
            "allowed": True,
            "next_status": target,
            "reason": "stable_boundary_with_supporting_evidence",
        }

    if target == "confirmed":
        if high_severity_contradiction:
            return {"allowed": False, "reason": "high_severity_contradiction"}
        if not required_evidence_complete:
            return {"allowed": False, "reason": "required_evidence_incomplete"}
        if not discriminating_action:
            return {"allowed": False, "reason": "discriminating_action_required"}
        return {
            "allowed": True,
            "next_status": target,
            "reason": "required_evidence_and_discriminating_action_complete",
        }

    if target == "rejected":
        if not high_severity_contradiction:
            return {"allowed": False, "reason": "rejection_requires_falsifier"}
        return {
            "allowed": True,
            "next_status": target,
            "reason": "falsifier_or_reproducible_contradiction",
        }

    return {"allowed": True, "next_status": target, "reason": "state_unchanged"}


def evaluate_knowledge_promotion(
    *,
    current: str,
    weakness_status: str,
    rca_status: str,
    valid_reproductions: int,
    valid_counterfactuals: int,
    lifecycle_complete: bool,
    direct_evidence: bool,
    applicability_complete: bool,
    regression_complete: bool,
    contradiction: bool,
) -> dict[str, Any]:
    """Evaluate knowledge-card promotion and demotion gates without mutation."""

    if current not in KNOWLEDGE_STATES:
        return {"allowed": False, "reason": "unknown_knowledge_state"}
    if weakness_status not in _WEAKNESS_STATUSES:
        return {"allowed": False, "reason": "unknown_weakness_status"}
    if rca_status not in RCA_STATES:
        return {"allowed": False, "reason": "unknown_rca_status"}

    if current == "none":
        if weakness_status not in {"candidate", "confirmed", "protected"}:
            return {"allowed": False, "reason": "weakness_status_not_eligible"}
        if contradiction:
            return {
                "allowed": True,
                "next_status": "provisional",
                "reason": "meaningful_counterexample",
            }
        return {
            "allowed": True,
            "next_status": "provisional",
            "reason": "provisional_case_created",
        }

    if current == "local_reusable":
        if weakness_status in {"unsupported", "environment_blocked", "rejected"}:
            return {"allowed": False, "reason": "weakness_status_not_eligible"}
        if contradiction:
            return {
                "allowed": True,
                "next_status": "contested",
                "reason": "meaningful_counterexample",
            }
        if rca_status == "rejected":
            return {"allowed": False, "reason": "rca_status_not_reusable"}
        return {
            "allowed": True,
            "next_status": "cross_project_pending",
            "reason": "requires_cross_project_review_or_replication",
        }

    if current == "cross_project_pending":
        if weakness_status not in {"confirmed", "protected"}:
            return {"allowed": False, "reason": "weakness_status_not_eligible"}
        if rca_status not in {"bounded", "confirmed"}:
            return {"allowed": False, "reason": "rca_status_not_reusable"}
        if valid_reproductions < MIN_STABLE_REPRODUCTIONS:
            return {"allowed": False, "reason": "reproduction_gate_incomplete"}
        if not direct_evidence:
            return {"allowed": False, "reason": "evidence_gate_incomplete"}
        if not all((lifecycle_complete, applicability_complete, regression_complete)):
            return {"allowed": False, "reason": "operational_card_fields_incomplete"}
        if contradiction:
            return {"allowed": False, "reason": "high_severity_contradiction"}
        return {
            "allowed": True,
            "next_status": "cross_project_reusable",
            "reason": "cross_project_reuse_gates_passed",
        }

    if current == "cross_project_reusable":
        if contradiction:
            return {
                "allowed": True,
                "next_status": "contested",
                "reason": "meaningful_counterexample",
            }
        return {
            "allowed": True,
            "next_status": "cross_project_reusable",
            "reason": "already_cross_project_reusable",
        }

    if contradiction:
        return {
            "allowed": True,
            "next_status": "provisional",
            "reason": "meaningful_counterexample",
        }

    if current == "provisional":
        if weakness_status not in {"confirmed", "protected"}:
            return {"allowed": False, "reason": "weakness_status_not_eligible"}
        if valid_reproductions < MIN_STABLE_REPRODUCTIONS:
            return {"allowed": False, "reason": "reproduction_gate_incomplete"}
        if not direct_evidence:
            return {"allowed": False, "reason": "evidence_gate_incomplete"}
        if not all((lifecycle_complete, applicability_complete, regression_complete)):
            return {"allowed": False, "reason": "operational_card_fields_incomplete"}
        if rca_status not in {"bounded", "confirmed"}:
            return {"allowed": False, "reason": "rca_status_not_reusable"}
        return {
            "allowed": True,
            "next_status": "local_reusable",
            "reason": "local_reuse_gates_passed",
        }

    return {"allowed": False, "reason": "promotion_not_allowed_from_current_state"}


# ---------------------------------------------------------------------------
# Deterministic evidence action planner (spec section 8).
# ---------------------------------------------------------------------------

_ACTION_REQUIRED_FIELDS = {
    "action_id",
    "kind",
    "hypotheses_separated",
    "evidence_gain",
    "cost",
    "risk",
    "environment_uncertainty",
    "preconditions",
    "cleanup",
    "output_schema",
}

# Read-only evidence sources are preferred before runtime experiments when the
# deterministic priority ties (spec section 8 ordering).
_KIND_PREFERENCE = {
    "evidence_lookup": 0,
    "event_lookup": 1,
    "source_lookup": 0,
    "config_lookup": 0,
    "log_lookup": 1,
    "trace_lookup": 1,
    "business_replay": 2,
    "dependency_replay": 2,
    "boundary_probe": 3,
    "isolated_counterfactual": 4,
    "new_injection": 5,
}


def _kind_rank(kind: Any) -> int:
    return _KIND_PREFERENCE.get(kind, _KIND_PREFERENCE["new_injection"])


def score_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Score one candidate evidence action without side effects."""

    errors = sorted(_ACTION_REQUIRED_FIELDS - set(action))
    if not action.get("cleanup"):
        errors.append("cleanup_contract_required")
    if not action.get("output_schema"):
        errors.append("output_schema_required")
    try:
        hypotheses_separated = int(action.get("hypotheses_separated", 0))
        evidence_gain = int(action.get("evidence_gain", 0))
        cost = int(action.get("cost", 0))
        risk = int(action.get("risk", 0))
        environment_uncertainty = int(action.get("environment_uncertainty", 0))
    except (TypeError, ValueError):
        errors.append("action metrics must be integers")
        return {"action_id": action.get("action_id"), "information_gain": 0, "total_cost": 0, "priority": 0, "errors": errors}
    information_gain = hypotheses_separated + evidence_gain
    total_cost = cost + risk + environment_uncertainty
    return {
        "action_id": action.get("action_id"),
        "information_gain": information_gain,
        "total_cost": total_cost,
        "priority": information_gain - total_cost,
        "errors": errors,
    }


def plan_next_action(
    actions: Iterable[Mapping[str, Any]],
    available_preconditions: set[str] | None = None,
) -> dict[str, Any]:
    """Select the highest-scoring safe action, or return pending with reasons."""

    available = set(available_preconditions or set())
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for action in actions:
        scored = score_action(action)
        missing = sorted(set(action.get("preconditions") or []) - available)
        if scored["errors"] or missing:
            rejected.append(
                {
                    "action_id": action.get("action_id"),
                    "errors": scored["errors"],
                    "missing_preconditions": missing,
                }
            )
            continue
        eligible.append({**action, "score": scored})
    if not eligible:
        return {"status": "pending", "reason": "no_safe_applicable_action", "rejected": rejected}
    selected = sorted(
        eligible,
        key=lambda item: (
            -item["score"]["priority"],
            _kind_rank(item.get("kind")),
            str(item["action_id"]),
        ),
    )[0]
    return {
        "status": "planned",
        "selected": selected,
        "rejected": rejected,
        "selection_reason": (
            "highest priority (information gain minus cost, risk and environment "
            "uncertainty) with read-only kinds preferred on ties"
        ),
    }
