"""Build a namespace-scoped NetworkChaos fallback for DNS traffic."""

from __future__ import annotations

import ipaddress
from typing import Any


def build_dns_network_fallback(
    *,
    namespace: str,
    selector: dict[str, str],
    dns_cluster_ip: str,
    dns_targets: list[str] | None = None,
    fault_family: str,
    duration_s: int,
    name: str,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    namespace = str(namespace or "").strip()
    family = str(fault_family or "").strip()
    if not namespace or not isinstance(selector, dict) or not selector:
        raise ValueError("namespace and selector are required")
    if family not in {"dns_failure", "dns_delay"}:
        raise ValueError("unsupported DNS fallback family")
    try:
        ipaddress.ip_address(str(dns_cluster_ip).strip())
    except ValueError as exc:
        raise ValueError("dns_cluster_ip must be a valid IP address") from exc
    if isinstance(duration_s, bool) or not isinstance(duration_s, int) or not 1 <= duration_s <= 3600:
        raise ValueError("duration_s must be an integer in [1, 3600]")
    targets = [str(item).strip() for item in (dns_targets or []) if str(item).strip()]
    if not targets:
        targets = [str(dns_cluster_ip).strip()]
    for target in targets:
        try:
            ipaddress.ip_address(target)
        except ValueError as exc:
            raise ValueError("dns_targets must contain valid IP addresses") from exc
    spec: dict[str, Any] = {
        "selector": {
            "namespaces": [namespace],
            "labelSelectors": {str(k): str(v) for k, v in sorted(selector.items())},
        },
        "mode": "one",
        "direction": "to",
        "externalTargets": targets,
        "duration": f"{duration_s}s",
    }
    if family == "dns_failure":
        spec.update({"action": "loss", "loss": {"loss": "100", "correlation": "100"}})
    else:
        if isinstance(latency_ms, bool) or not isinstance(latency_ms, int) or not 1 <= latency_ms <= 300_000:
            raise ValueError("latency_ms must be an integer in [1, 300000]")
        spec.update({"action": "delay", "delay": {"latency": f"{latency_ms}ms"}})
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "NetworkChaos",
        "metadata": {
            "name": str(name).strip(),
            "namespace": namespace,
            "labels": {
                "chaosatlas.dev/owner": "chaosatlas",
                "chaosatlas.dev/fault-family": family,
            },
        },
        "spec": spec,
    }
