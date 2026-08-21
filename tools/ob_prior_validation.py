"""Pure timeline reduction for the OB cross-project prior validation.

No cluster access here; tools/run_ob_prior_validation.py performs the run and
feeds captured samples into these reducers so the classification is
independently testable.

Arm A (singleton outage) expectation: during the kill window the business
oracle fails while NONE of the pods that were Ready before injection is
still serving (the pre-injection pod set is gone; at most a just-created
replacement exists). This survives the observed race where a fast
replacement re-registers into Service endpoints before the business path
has recovered. An early HTTP 200 with no ready endpoint at all is still
recorded as an observation-window artifact, not defense (the lesson
imported from the sock-shop round).

Arm B (two-replica defended) expectation: at least one synchronized sample
proves business HTTP 200 served through a surviving (non-killed) Ready pod
IP present in the target Service endpoints.
"""

from __future__ import annotations

from typing import Any


def _ready_pod_ips(pods: dict[str, Any]) -> set[str]:
    ips: set[str] = set()
    for pod in pods.get("items") or []:
        conditions = ((pod.get("status") or {}).get("conditions") or [])
        ready = any(
            isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True"
            for c in conditions
        )
        ip = ((pod.get("status") or {}).get("podIP") or "")
        if ready and ip:
            ips.add(str(ip))
    return ips


def _endpoint_ips(endpoints: dict[str, Any], *, not_ready: bool = False) -> set[str]:
    ips: set[str] = set()
    for subset in endpoints.get("subsets") or []:
        addresses = subset.get("notReadyAddresses" if not_ready else "addresses") or []
        for addr in addresses:
            if isinstance(addr, dict) and addr.get("ip"):
                ips.add(str(addr["ip"]))
    return ips


def _business_ok(sample: dict[str, Any]) -> bool:
    business = sample.get("business") or {}
    return bool(business.get("contract_ok")) and business.get("status_code") == 200


def _ready_uids(pods: dict[str, Any]) -> set[str]:
    uids: set[str] = set()
    for pod in pods.get("items") or []:
        conditions = ((pod.get("status") or {}).get("conditions") or [])
        ready = any(
            isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True"
            for c in conditions
        )
        uid = str((pod.get("metadata") or {}).get("uid") or "")
        if ready and uid:
            uids.add(uid)
    return uids


def reduce_arm_a(samples: list[dict[str, Any]], pre_injection_ready_uids: set[str]) -> dict[str, Any]:
    """Classify the singleton-outage arm from synchronized samples.

    An outage sample is a business failure while no pod that was Ready
    before injection is still Ready: the singleton's serving capacity is
    gone and only a replacement (if any) exists.
    """
    outage_samples = 0
    artifact_samples = 0
    for sample in samples:
        ready_endpoints = _endpoint_ips(sample.get("endpoints") or {})
        business_ok = _business_ok(sample)
        pre_still_ready = _ready_uids(sample.get("pods") or {}) & set(pre_injection_ready_uids)
        if not pre_still_ready:
            if ready_endpoints and business_ok:
                continue  # replacement already serving: normal recovery, not evidence
            if business_ok:
                artifact_samples += 1
            else:
                outage_samples += 1
    if outage_samples:
        return {
            "classification": "weakness_reproduced",
            "deterministic": True,
            "outage_sample_count": outage_samples,
            "observation_window_artifact_count": artifact_samples,
            "sample_count": len(samples),
            "reason": "business oracle failed while no pre-injection Ready pod was still serving",
        }
    return {
        "classification": "observation_inconclusive",
        "deterministic": False,
        "outage_sample_count": outage_samples,
        "observation_window_artifact_count": artifact_samples,
        "sample_count": len(samples),
        "reason": "no synchronized outage sample was captured; the prior is not validated by this arm",
    }


def reduce_arm_b(samples: list[dict[str, Any]], killed_uid: str) -> dict[str, Any]:
    """Classify the two-replica defended arm with UID co-proof."""
    co_proof = 0
    for sample in samples:
        if not _business_ok(sample):
            continue
        surviving_ready = _surviving_ready_ips(sample.get("pods") or {}, killed_uid)
        endpoint_ips = _endpoint_ips(sample.get("endpoints") or {})
        if surviving_ready & endpoint_ips:
            co_proof += 1
    defended = {
        "classification": "defended",
        "deterministic": True,
        "defended_sample_count": co_proof,
        "sample_count": len(samples),
        "reason": "HTTP 200 persisted through a non-killed Ready pod IP in Service endpoints",
    } if co_proof else {
        "classification": "observation_inconclusive",
        "deterministic": False,
        "defended_sample_count": 0,
        "sample_count": len(samples),
        "reason": "no synchronized sample proved surviving-replica service; the prior is not validated by this arm",
    }
    return defended


def _surviving_ready_ips(pods: dict[str, Any], killed_uid: str) -> set[str]:
    ips: set[str] = set()
    for pod in pods.get("items") or []:
        uid = str((pod.get("metadata") or {}).get("uid") or "")
        conditions = ((pod.get("status") or {}).get("conditions") or [])
        ready = any(
            isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True"
            for c in conditions
        )
        ip = ((pod.get("status") or {}).get("podIP") or "")
        if ready and ip and uid and uid != killed_uid:
            ips.add(str(ip))
    return ips


def summarize_prior_validation(
    *,
    arm_a: dict[str, Any],
    arm_b: dict[str, Any],
    cleanup_ok: bool,
    restored_replicas: int | None,
    residual_chaos_count: int,
) -> dict[str, Any]:
    """Final verdict for the projected prior on the target project."""
    arm_a_ok = arm_a.get("classification") == "weakness_reproduced"
    arm_b_ok = arm_b.get("classification") == "defended"
    lifecycle_ok = cleanup_ok and restored_replicas == 1 and residual_chaos_count == 0
    if arm_a_ok and arm_b_ok and lifecycle_ok:
        verdict = "prior_validated"
        reason = "both arms reproduced their expected mechanism and the lifecycle was restored cleanly"
    elif not lifecycle_ok:
        verdict = "lifecycle_invalid"
        reason = "cleanup, replica restoration, or residual-chaos checks failed; no knowledge claim may be derived"
    else:
        verdict = "not_validated"
        reason = "at least one arm failed to reproduce the expected mechanism; the prior stays provisional"
    return {
        "verdict": verdict,
        "reason": reason,
        "arm_a": arm_a,
        "arm_b": arm_b,
        "lifecycle": {
            "cleanup_ok": cleanup_ok,
            "restored_replicas": restored_replicas,
            "residual_chaos_count": residual_chaos_count,
        },
    }
