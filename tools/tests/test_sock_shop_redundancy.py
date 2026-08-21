from __future__ import annotations

from tools.sock_shop_redundancy import classify_redundancy_sample, summarize_redundancy_timeline


def _pod(uid: str, ip: str, *, ready: bool = True) -> dict:
    return {
        "metadata": {"name": f"front-end-{uid}", "uid": uid},
        "status": {
            "phase": "Running",
            "podIP": ip,
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
        },
    }


def _endpoints(*records: tuple[str, str]) -> dict:
    return {
        "kind": "Endpoints",
        "subsets": [{
            "addresses": [
                {"ip": ip, "targetRef": {"uid": uid, "kind": "Pod"}}
                for ip, uid in records
            ]
        }],
    }


def test_redundancy_requires_non_killed_ready_endpoint_and_business_success():
    result = classify_redundancy_sample(
        pods={"items": [_pod("killed", "10.0.0.1", ready=False), _pod("survivor", "10.0.0.2")]},
        endpoints=_endpoints(("10.0.0.2", "survivor")),
        business={"status_code": 200, "contract_ok": True},
        killed_uid="killed",
    )
    assert result["classification"] == "defended"
    assert result["surviving_ready_endpoint_uids"] == ["survivor"]
    assert result["deterministic"] is True


def test_redundancy_does_not_promote_http_success_without_uid_matched_endpoint():
    result = classify_redundancy_sample(
        pods={"items": [_pod("killed", "10.0.0.1", ready=False), _pod("survivor", "10.0.0.2")]},
        endpoints={"kind": "Endpoints", "subsets": [{"addresses": [{"ip": "10.0.0.2"}]}]},
        business={"status_code": 200, "contract_ok": True},
        killed_uid="killed",
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False


def test_redundancy_summary_accepts_one_proven_defended_sample():
    timeline = [
        {
            "pods": {"items": [_pod("killed", "10.0.0.1", ready=False), _pod("survivor", "10.0.0.2")]},
            "endpoints": _endpoints(("10.0.0.2", "survivor")),
            "business": {"status_code": 200, "contract_ok": True},
        },
        {
            "pods": {"items": [_pod("survivor", "10.0.0.2")]},
            "endpoints": _endpoints(("10.0.0.2", "survivor")),
            "business": {"status_code": None, "error": "connection_reset", "contract_ok": False},
        },
    ]
    result = summarize_redundancy_timeline(pod_before={"items": [_pod("killed", "10.0.0.1"), _pod("survivor", "10.0.0.2")]}, samples=timeline, killed_uid="killed")
    assert result["classification"] == "defended"
    assert result["deterministic"] is True
    assert result["defended_sample_count"] == 1


def test_redundancy_summary_is_inconclusive_when_no_sample_proves_defense():
    result = summarize_redundancy_timeline(
        pod_before={"items": [_pod("killed", "10.0.0.1"), _pod("survivor", "10.0.0.2")]},
        samples=[{
            "pods": {"items": [_pod("killed", "10.0.0.1", ready=False), _pod("survivor", "10.0.0.2")]},
            "endpoints": {"kind": "Endpoints", "subsets": []},
            "business": {"status_code": 200, "contract_ok": True},
        }],
        killed_uid="killed",
    )
    assert result["classification"] == "observation_inconclusive"
    assert result["deterministic"] is False
