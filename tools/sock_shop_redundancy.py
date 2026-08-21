"""Deterministic evidence rules for the Sock Shop two-replica PodKill control."""

from __future__ import annotations

from typing import Any


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    items = value.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _pod_uid(pod: dict[str, Any]) -> str | None:
    value = (pod.get("metadata") or {}).get("uid")
    return str(value) if value else None


def _pod_ip(pod: dict[str, Any]) -> str | None:
    value = (pod.get("status") or {}).get("podIP")
    return str(value) if value else None


def _ready(pod: dict[str, Any]) -> bool:
    return any(
        isinstance(condition, dict)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in ((pod.get("status") or {}).get("conditions") or [])
    )


def _endpoint_records(endpoints: dict[str, Any]) -> tuple[list[dict[str, str]], bool]:
    if not isinstance(endpoints, dict) or "subsets" not in endpoints:
        return [], False
    subsets = endpoints.get("subsets")
    if not isinstance(subsets, list):
        return [], True
    records: list[dict[str, str]] = []
    for subset in subsets:
        if not isinstance(subset, dict):
            continue
        for address in subset.get("addresses") or []:
            if not isinstance(address, dict) or not address.get("ip"):
                continue
            target = address.get("targetRef") or {}
            uid = target.get("uid") if isinstance(target, dict) else None
            records.append({"ip": str(address["ip"]), "uid": str(uid) if uid else ""})
    return records, True


def classify_redundancy_sample(
    *,
    pods: dict[str, Any],
    endpoints: dict[str, Any],
    business: dict[str, Any],
    killed_uid: str,
) -> dict[str, Any]:
    """Classify one synchronized sample, requiring endpoint-to-Pod UID proof."""

    pod_items = _items(pods)
    records, endpoint_observed = _endpoint_records(endpoints)
    ready_uids = {
        uid for pod in pod_items if _ready(pod) and (uid := _pod_uid(pod)) and uid != killed_uid
    }
    endpoint_uids = {record["uid"] for record in records if record["uid"]}
    surviving = sorted(ready_uids & endpoint_uids)
    contract_ok = (
        str(business.get("status_code", business.get("http_status"))) == "200"
        and business.get("contract_ok", True) is not False
    )
    transport_unavailable = bool(business.get("error")) or business.get("status_code", business.get("http_status")) is None
    has_complete_identity = bool(pod_items) and all(_pod_uid(pod) for pod in pod_items) and bool(killed_uid)
    if not endpoint_observed or not has_complete_identity or not surviving:
        classification = "platform_blocked" if transport_unavailable else "observation_inconclusive"
        deterministic = bool(transport_unavailable and endpoint_observed and has_complete_identity)
        reason = (
            "business path was unavailable at the platform boundary"
            if deterministic
            else "no non-killed Ready Pod UID was proven in Service endpoints"
        )
    elif not contract_ok:
        classification = "platform_blocked" if transport_unavailable else "observation_inconclusive"
        deterministic = bool(transport_unavailable)
        reason = "business path was unavailable at the platform boundary" if deterministic else "business contract failed"
    else:
        classification = "defended"
        deterministic = True
        reason = "HTTP 200 persisted through a non-killed Ready Pod UID in Service endpoints"
    return {
        "classification": classification,
        "deterministic": deterministic,
        "business_success": contract_ok,
        "endpoint_observed": endpoint_observed,
        "endpoint_uids": sorted(endpoint_uids),
        "ready_pod_uids": sorted(ready_uids),
        "surviving_ready_endpoint_uids": surviving,
        "killed_uid": killed_uid,
        "reason": reason,
    }


def summarize_redundancy_timeline(
    *,
    pod_before: dict[str, Any],
    samples: list[dict[str, Any]],
    killed_uid: str,
) -> dict[str, Any]:
    per_sample = [
        classify_redundancy_sample(
            pods=sample.get("pods") if isinstance(sample.get("pods"), dict) else {},
            endpoints=sample.get("endpoints") if isinstance(sample.get("endpoints"), dict) else {},
            business=sample.get("business") if isinstance(sample.get("business"), dict) else {},
            killed_uid=killed_uid,
        )
        for sample in samples
        if isinstance(sample, dict)
    ]
    defended_count = sum(item["classification"] == "defended" for item in per_sample)
    if defended_count:
        classification, deterministic, reason = "defended", True, "at least one synchronized sample proves redundant service capacity"
    elif per_sample and all(item["classification"] == "platform_blocked" for item in per_sample):
        classification, deterministic, reason = "platform_blocked", True, "all synchronized samples were unavailable at the platform boundary"
    else:
        classification, deterministic, reason = "observation_inconclusive", False, "no synchronized sample proves redundant service capacity"
    return {
        "classification": classification,
        "deterministic": deterministic,
        "sample_count": len(per_sample),
        "defended_sample_count": defended_count,
        "sample_classifications": [item["classification"] for item in per_sample],
        "per_sample": per_sample,
        "baseline_pod_uids": sorted({_pod_uid(pod) for pod in _items(pod_before) if _pod_uid(pod)}),
        "killed_uid": killed_uid,
        "reason": reason,
    }
