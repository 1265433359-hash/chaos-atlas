"""Pure availability and recovery oracles for deployment-level experiments."""

from __future__ import annotations

from typing import Any, Iterable


def _available(sample: Any) -> int:
    if isinstance(sample, bool):
        return int(sample)
    if isinstance(sample, (int, float)):
        return max(0, int(sample))
    if isinstance(sample, dict):
        for key in ("availableReplicas", "available_replicas", "available"):
            value = sample.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return max(0, int(value))
    # The CE-compatible rule treats an unavailable API observation as zero.
    return 0


def availability_ratio(samples: Iterable[Any], minimum_available: int = 1) -> float:
    values = list(samples)
    if not values:
        return 0.0
    minimum = max(0, int(minimum_available))
    return sum(_available(item) >= minimum for item in values) / len(values)


def max_zero_streak(samples: Iterable[Any]) -> int:
    longest = current = 0
    for sample in samples:
        if _available(sample) <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _elapsed(sample: dict[str, Any]) -> float | None:
    for key in ("elapsed_s", "time_s", "timestamp_s"):
        value = sample.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def recovery_deadline(samples: Iterable[dict[str, Any]], deadline_s: float) -> float | None:
    """Return first elapsed recovery time within deadline, or ``None``."""
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if sample.get("ready") is True and sample.get("business_probe") is True:
            elapsed = _elapsed(sample)
            if elapsed is not None and elapsed <= float(deadline_s):
                return elapsed
    return None


def replacement_identity(before: Iterable[Any], after: Iterable[Any]) -> bool:
    before_uids = {str(item.get("uid")) for item in before if isinstance(item, dict) and item.get("uid")}
    after_uids = {str(item.get("uid")) for item in after if isinstance(item, dict) and item.get("uid")}
    return bool(before_uids and after_uids and bool(after_uids - before_uids) and not before_uids.intersection(after_uids))


def business_probe_stability(samples: Iterable[dict[str, Any]], k: int) -> bool:
    values = list(samples)
    if k <= 0 or len(values) < k:
        return False
    streak = 0
    for sample in values:
        ok = isinstance(sample, dict) and (sample.get("business_probe") is True or sample.get("probe_ok") is True)
        streak = streak + 1 if ok else 0
        if streak >= k:
            return True
    return False


def classify_recovery(
    before: Iterable[Any], after: Iterable[dict[str, Any]], *,
    stable_probe_samples: Iterable[dict[str, Any]], cleanup_confirmed: bool,
    deadline_s: float, stable_probe_k: int = 1,
) -> str:
    before_list, after_list = list(before), list(after)
    if not cleanup_confirmed:
        return "cleanup_incomplete"
    if any(isinstance(item, dict) and item.get("probe_restart_escape") for item in after_list):
        return "probe_restart_escape"
    if not replacement_identity(before_list, after_list):
        return "no_readiness_false_recovery"
    if not any(isinstance(item, dict) and item.get("ready") is True for item in after_list):
        return "no_readiness_false_recovery"
    if not business_probe_stability(stable_probe_samples, stable_probe_k):
        return "no_readiness_false_recovery"
    if recovery_deadline(after_list, deadline_s) is None:
        return "recovery_timeout"
    return "recovered"


def classify_availability(samples: Iterable[Any], *, minimum_available: int, ratio_threshold: float, max_zero_streak_limit: int) -> str:
    values = list(samples)
    if not values:
        return "platform_blocked"
    ratio = availability_ratio(values, minimum_available)
    if ratio >= ratio_threshold and max_zero_streak(values) <= max_zero_streak_limit:
        return "availability_defended"
    return "availability_degraded"


def build_oracle_result(samples: Iterable[Any], profile: dict[str, Any]) -> dict[str, Any]:
    ce = profile.get("ce_steady_state") or {}
    values = list(samples)
    return {"label": classify_availability(values, minimum_available=int(ce.get("minimum_available", 1)), ratio_threshold=float(ce.get("ratio_threshold", 0.99)), max_zero_streak_limit=int(ce.get("max_zero_streak", 1))), "metric": ce.get("metric", "deployment.availableReplicas"), "sample_count": len(values), "availability_ratio": availability_ratio(values, int(ce.get("minimum_available", 1))), "max_zero_streak": max_zero_streak(values)}

