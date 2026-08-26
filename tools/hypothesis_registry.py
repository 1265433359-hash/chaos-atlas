"""Build advisory project portraits and evidence-bounded hypothesis registries."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from typing import Any


_KIND_ORDER = {
    "architecture": 0,
    "configuration": 1,
    "dependency": 2,
    "runtime": 3,
    "defense": 4,
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _slug(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", _text(value, "unknown")).strip("-")
    return text.lower() or "unknown"


def _replicas(deployment: dict[str, Any]) -> int | None:
    value = deployment.get("desired_replicas")
    if value is None:
        value = (deployment.get("spec") or {}).get("replicas")
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _deployment_records(inventory: dict[str, Any], detection: dict[str, Any]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for node in detection.get("deployment_nodes") or []:
        if not isinstance(node, dict):
            continue
        deployment = node.get("deployment") if isinstance(node.get("deployment"), dict) else {}
        name = _text(deployment.get("name"))
        if name:
            records[name] = deepcopy(node)
    for deployment in inventory.get("deployments") or []:
        if not isinstance(deployment, dict):
            continue
        name = _text(deployment.get("name") or (deployment.get("metadata") or {}).get("name"))
        if name and name not in records:
            records[name] = deepcopy(deployment)
    return [records[name] for name in sorted(records)]


def _normalized_deployment(record: dict[str, Any]) -> dict[str, Any]:
    deployment = record.get("deployment") if isinstance(record.get("deployment"), dict) else record
    availability = record.get("availability_profile") if isinstance(record.get("availability_profile"), dict) else {}
    resources = deployment.get("resources") if isinstance(deployment.get("resources"), dict) else {}
    return {
        "name": _text(deployment.get("name") or (deployment.get("metadata") or {}).get("name")),
        "desired_replicas": _replicas(deployment),
        "containers": [str(item) for item in deployment.get("containers") or []],
        "resources": {
            "requests": deepcopy(resources.get("requests") or {}),
            "limits": deepcopy(resources.get("limits") or {}),
        },
        "service": _text((record.get("service") or {}).get("name")) if isinstance(record.get("service"), dict) else "",
        "availability": {
            "pdb": deepcopy(availability.get("pdb")) if "pdb" in availability else None,
            "readiness_probe": deepcopy(availability.get("readiness_probe") or {}),
            "liveness_probe": deepcopy(availability.get("liveness_probe") or {}),
            "manifest_facts_status": _text(availability.get("manifest_facts_status"), "unknown"),
        },
    }


def build_project_portrait(
    inventory: dict[str, Any],
    detection: dict[str, Any],
    candidate_space: dict[str, Any],
    *,
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize verified project facts into an advisory, hashable portrait."""
    deployments = [_normalized_deployment(item) for item in _deployment_records(inventory, detection)]
    services = []
    for item in inventory.get("services") or []:
        if isinstance(item, str):
            services.append(item)
        elif isinstance(item, dict):
            services.append(_text(item.get("name") or (item.get("metadata") or {}).get("name")))
    services = sorted({item for item in services if item})
    candidates = [item for item in candidate_space.get("candidates") or [] if isinstance(item, dict)]
    families = sorted({_text(item.get("fault_family")) for item in candidates if _text(item.get("fault_family"))})
    portrait = {
        "schema_version": "chaosatlas-project-portrait-v1",
        "project_id": _text(inventory.get("project_id")),
        "project_commit": _text(inventory.get("project_commit")),
        "namespace": _text(inventory.get("namespace")),
        "deployment_count": len(deployments),
        "service_count": len(services),
        "deployments": deployments,
        "services": services,
        "dependencies": deepcopy([item for item in inventory.get("dependencies") or [] if isinstance(item, dict)]),
        "business_oracles": deepcopy([item for item in inventory.get("business_oracles") or [] if isinstance(item, dict)]),
        "candidate_coverage": {
            "candidate_count": len(candidates),
            "fault_families": families,
            "candidate_ids": [str(item.get("candidate_id")) for item in candidates if item.get("candidate_id")],
        },
        "knowledge_card_ids": sorted(
            {_text(item.get("id") or item.get("weakness_id")) for item in (cards or []) if isinstance(item, dict) and _text(item.get("id") or item.get("weakness_id"))}
        ),
        "claim_scope": "advisory",
    }
    portrait["input_sha256"] = _hash(portrait)
    return portrait


def _advisory_by_candidate(advisory: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("candidate_id")): item
        for item in (advisory or {}).get("hypotheses") or []
        if isinstance(item, dict) and item.get("candidate_id")
    }


def build_hypothesis_registry(
    inventory: dict[str, Any],
    detection: dict[str, Any],
    candidate_space: dict[str, Any],
    *,
    advisory: dict[str, Any] | None = None,
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate broad advisory hypotheses without making runtime conclusions."""
    items: dict[str, dict[str, Any]] = {}
    advisory_by_candidate = _advisory_by_candidate(advisory)

    def add(
        *,
        kind: str,
        target: str,
        mechanism: str,
        target_kind: str,
        preconditions: list[str],
        expected_observations: list[str],
        falsifiers: list[str],
        required_evidence: list[str],
        priority_score: int,
        execution_eligible: bool = False,
        candidate_id: str | None = None,
        source: str = "deterministic",
    ) -> None:
        hypothesis_id = f"{kind}:{_slug(target)}:{_slug(mechanism)}"
        items[hypothesis_id] = {
            "hypothesis_id": hypothesis_id,
            "kind": kind,
            "target": target,
            "target_kind": target_kind,
            "candidate_id": candidate_id,
            "mechanism": mechanism,
            "preconditions": sorted(set(preconditions)),
            "expected_observations": sorted(set(expected_observations)),
            "falsifiers": sorted(set(falsifiers)),
            "required_evidence": sorted(set(required_evidence)),
            "priority_score": int(priority_score),
            "execution_eligible": bool(execution_eligible),
            "source": source,
            "claim_scope": "advisory",
        }

    for candidate in candidate_space.get("candidates") or []:
        if not isinstance(candidate, dict) or not candidate.get("candidate_id"):
            continue
        candidate_id = str(candidate["candidate_id"])
        family = _text(candidate.get("fault_family"), "runtime_fault")
        target = _text(candidate.get("target"))
        supplied = advisory_by_candidate.get(candidate_id) or {}
        add(
            kind="runtime",
            target=target,
            target_kind=_text(candidate.get("target_kind"), "deployment"),
            mechanism=family,
            candidate_id=candidate_id,
            preconditions=["candidate passes applicability gate", "business oracle baseline succeeds"],
            expected_observations=[str(item) for item in supplied.get("expected_observations") or ["business oracle result", "recovery and cleanup evidence"]],
            falsifiers=["confirmed injection leaves the independent business oracle within baseline"],
            required_evidence=["baseline_oracle", "injection_confirmation", "observation", "recovery", "cleanup"],
            priority_score=50,
            execution_eligible=True,
            source="advisory" if supplied else "deterministic",
        )
        if supplied.get("mechanism"):
            for generated in items.values():
                if generated.get("candidate_id") == candidate_id:
                    generated["advisory_mechanism"] = str(supplied["mechanism"])
                    break

    for record in _deployment_records(inventory, detection):
        deployment = _normalized_deployment(record)
        target = deployment["name"]
        if not target:
            continue
        if deployment["desired_replicas"] == 1:
            add(
                kind="architecture",
                target=target,
                target_kind="deployment",
                mechanism="singleton_availability",
                preconditions=["desired replica count is one"],
                expected_observations=["single target disruption can remove the only service endpoint"],
                falsifiers=["independent endpoint remains available during one target disruption"],
                required_evidence=["deployment_replicas", "service_endpoints", "business_oracle"],
                priority_score=90,
            )
            add(
                kind="defense",
                target=target,
                target_kind="deployment",
                mechanism="redundancy_preserves_route",
                preconditions=["at least two ready replicas are available"],
                expected_observations=["business oracle remains within baseline while one replica is disrupted"],
                falsifiers=["service has no ready endpoint during one replica disruption"],
                required_evidence=["replica_count", "endpoint_continuity", "business_oracle", "recovery"],
                priority_score=75,
            )
        availability = deployment["availability"]
        # A missing or unverified PDB is an evidence-bounded hypothesis, never a
        # runtime weakness verdict.  This is intentionally emitted even when
        # manifest facts are incomplete so the next evidence pass can resolve it.
        if availability["pdb"] is None:
            add(
                kind="configuration",
                target=target,
                target_kind="deployment",
                mechanism="pdb_coverage_needs_verification",
                preconditions=["PDB facts are not verified"],
                expected_observations=["voluntary disruption policy is documented"],
                falsifiers=["PDB object verifies an appropriate availability budget"],
                required_evidence=["pdb"],
                priority_score=60,
            )
        limits = deployment["resources"].get("limits") or {}
        if deployment["resources"] and not limits:
            add(
                kind="configuration",
                target=target,
                target_kind="deployment",
                mechanism="resource_limits_need_verification",
                preconditions=["container resource facts are available"],
                expected_observations=["resource pressure remains bounded under stress"],
                falsifiers=["container limits are explicitly configured"],
                required_evidence=["deployment_resources", "metrics_or_events"],
                priority_score=45,
            )
        if not availability["readiness_probe"]:
            add(
                kind="configuration",
                target=target,
                target_kind="deployment",
                mechanism="readiness_probe_need_verification",
                preconditions=["readiness probe facts are not verified"],
                expected_observations=["unready targets are removed from service endpoints"],
                falsifiers=["readiness probe is explicitly configured and observed"],
                required_evidence=["readiness_probe", "service_endpoints", "business_oracle"],
                priority_score=55,
            )

    for edge in inventory.get("dependencies") or []:
        if not isinstance(edge, dict):
            continue
        source = _text(edge.get("source"))
        target = _text(edge.get("target"))
        if not source or not target:
            continue
        add(
            kind="dependency",
            target=f"{source}->{target}",
            target_kind="service_edge",
            mechanism="dependency_availability",
            preconditions=["dependency edge is present in the project portrait"],
            expected_observations=["upstream behavior remains within the business contract when the dependency is impaired"],
            falsifiers=["business oracle remains within baseline under dependency impairment"],
            required_evidence=["dependency_edge", "business_oracle", "dependency_runtime_evidence"],
            priority_score=65,
        )

    ordered = sorted(
        items.values(),
        key=lambda item: (-item["priority_score"], _KIND_ORDER.get(item["kind"], 99), item["hypothesis_id"]),
    )
    counts = Counter(item["kind"] for item in ordered)
    registry = {
        "schema_version": "chaosatlas-hypothesis-registry-v1",
        "project_id": _text(inventory.get("project_id")),
        "project_commit": _text(inventory.get("project_commit")),
        "namespace": _text(inventory.get("namespace")),
        "hypothesis_count": len(ordered),
        "execution_eligible_count": sum(1 for item in ordered if item["execution_eligible"]),
        "candidate_ids": [str(item.get("candidate_id")) for item in ordered if item.get("candidate_id")],
        "counts": {key: counts.get(key, 0) for key in _KIND_ORDER},
        "coverage": {
            "kinds": sorted(counts),
            "targets": sorted({_text(item.get("target")) for item in ordered}),
            "runtime_fault_families": sorted({_text(item.get("mechanism")) for item in ordered if item["kind"] == "runtime"}),
        },
        "hypotheses": ordered,
        "claim_scope": "advisory",
    }
    registry["input_sha256"] = _hash(
        {
            "inventory": inventory,
            "detection": detection,
            "candidate_space": candidate_space,
            "advisory": advisory or {},
            "cards": cards or [],
        }
    )
    return registry
