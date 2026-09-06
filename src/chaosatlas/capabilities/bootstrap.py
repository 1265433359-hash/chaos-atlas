"""Composition boundary for read-only 32+9 project capability discovery."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from chaosatlas.capabilities.contracts import (
    aggregate_capability_status,
    canonical_catalog_ids,
    strongest_evidence_grade,
    validate_capability_record,
    validate_catalog_coverage,
)
from chaosatlas.capabilities.core_assessment import assess_core_capabilities
from chaosatlas.capabilities.evidence import CapabilityEvidenceIndex
from chaosatlas.capabilities.extension_assessment import assess_extension_capabilities
from chaosatlas.capabilities.runtime_probe import probe_runtime_backends


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _without_volatile(value: Any) -> Any:
    """Remove observation timestamps before deriving deterministic identities."""
    if isinstance(value, dict):
        return {
            key: _without_volatile(item)
            for key, item in value.items()
            if key not in {"checked_at", "started_at", "finished_at"}
        }
    if isinstance(value, list):
        return [_without_volatile(item) for item in value]
    return value


def _aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get("fault_id") or "")].append(record)
    core_ids, extension_ids = canonical_catalog_ids()
    scopes = {fault_id: "core" for fault_id in core_ids} | {fault_id: "extension" for fault_id in extension_ids}
    result: list[dict[str, Any]] = []
    for fault_id in [*core_ids, *extension_ids]:
        items = groups.get(fault_id) or []
        if not items:
            raise ValueError(f"target matrix has no record for {fault_id}")
        status = aggregate_capability_status(item.get("capability_status") for item in items)
        result.append({
            "fault_id": fault_id,
            "catalog_scope": scopes[fault_id],
            "capability_status": status,
            "evidence_grade": strongest_evidence_grade(item.get("evidence_grade") for item in items),
            "required_isolation": min((str(item.get("required_isolation") or "L3") for item in items)),
            "candidate_eligible": any(item.get("candidate_eligible") is True for item in items),
            "target_record_count": len(items),
            "status_counts": dict(sorted(Counter(str(item.get("capability_status")) for item in items).items())),
            "reason_codes": sorted({str(item.get("reason_code") or "") for item in items if item.get("reason_code")}),
            "prerequisites": sorted({value for item in items for value in item.get("prerequisites") or []}),
            "oracle_ids": sorted({value for item in items for value in item.get("oracle_ids") or []}),
            "evidence_refs": sorted({ref for item in items for ref in item.get("evidence_refs") or []}),
        })
    return result


class CapabilityBootstrapper:
    """Build a complete target matrix without mutating Kubernetes or profiles."""

    def __init__(self, *, profile: dict[str, Any], adapter: Any, evidence_index: CapabilityEvidenceIndex | None = None, runtime_evidence_root: str | Path | None = None) -> None:
        self.profile = deepcopy(profile)
        self.adapter = adapter
        self.evidence_index = evidence_index or CapabilityEvidenceIndex.empty()
        self.runtime_evidence_root = runtime_evidence_root

    def run(self) -> dict[str, Any]:
        inventory = self.adapter.inventory()
        if inventory.get("status") != "verified":
            return {
                "schema_version": "chaosatlas-capability-bootstrap-v1",
                "status": "environment_blocked",
                "project_id": self.profile.get("project_id"),
                "errors": list(inventory.get("errors") or ["inventory is unavailable"]),
                "warnings": list(inventory.get("warnings") or []),
                "read_only": True,
                "injection_performed": False,
            }
        detection = self.adapter.build_capability_nodes(inventory)
        if detection.get("status") != "verified":
            return {
                "schema_version": "chaosatlas-capability-bootstrap-v1",
                "status": "method_invalid",
                "project_id": self.profile.get("project_id"),
                "errors": list(detection.get("errors") or ["target discovery failed"]),
                "warnings": list(inventory.get("warnings") or []),
                "read_only": True,
                "injection_performed": False,
            }
        nodes = list(detection.get("deployment_nodes") or [])
        kube_context = str(getattr(self.adapter, "kube_context", "") or "") or None
        runtime = probe_runtime_backends(
            runner=self.adapter.runner,
            kube_context=kube_context,
            evidence_root=self.runtime_evidence_root,
        )
        core = assess_core_capabilities(self.profile, nodes, runtime)
        extensions = assess_extension_capabilities(
            self.profile,
            nodes,
            list(inventory.get("dependencies") or []),
            runtime,
        )
        records = [*core, *extensions]
        for record in records:
            evidence = self.evidence_index.lookup(
                project_id=str(record.get("project_id") or ""),
                project_revision=str(record.get("project_revision") or ""),
                target=record.get("target"),
                fault_id=str(record.get("fault_id") or ""),
            )
            if evidence["evidence_grade"] in {"E2", "E3", "E4"}:
                record["evidence_grade"] = evidence["evidence_grade"]
                record["evidence_refs"] = evidence["evidence_refs"]
                record["valid_run_count"] = evidence["valid_run_count"]
                record["stable_reproduction_count"] = evidence["stable_reproduction_count"]
                if record["capability_status"] in {"canary_required", "supported"}:
                    record["capability_status"] = "supported"
                    record["reason_code"] = "runtime_evidence_verified"
                    record["reason"] = "valid live lifecycle evidence was found in the external evidence index"
                # Historical proof is retained, but never overrides a current
                # blocked/inapplicable/unsupported execution boundary.
        record_errors = [
            f"{item.get('fault_id')}@{item.get('target_id')}: {error}"
            for item in records
            for error in validate_capability_record(item)
        ]
        aggregate = _aggregate(records)
        coverage_errors = validate_catalog_coverage(aggregate)
        errors = [*record_errors, *coverage_errors]
        stable = {
            "project_id": self.profile.get("project_id"),
            "project_revision": self.profile.get("project_commit"),
            "runtime": {key: value for key, value in runtime.items() if key != "checked_at"},
            "targets": nodes,
            "target_capabilities": records,
            "project_capabilities": aggregate,
        }
        return {
            "schema_version": "chaosatlas-capability-bootstrap-v1",
            "status": "verified" if not errors else "method_invalid",
            "project_id": self.profile.get("project_id"),
            "project_revision": self.profile.get("project_commit"),
            "catalog": {"core": 32, "extension": 9, "total": 41},
            "target_count": len(nodes),
            "target_capability_count": len(records),
            "targets": nodes,
            "runtime": runtime,
            "target_capabilities": records,
            "project_capabilities": aggregate,
            "status_counts": dict(sorted(Counter(item["capability_status"] for item in aggregate).items())),
            "errors": errors,
            "warnings": [*list(inventory.get("warnings") or []), *self.evidence_index.warnings],
            "input_snapshot_sha256": _canonical_hash(_without_volatile({"profile": self.profile, "inventory": inventory, "runtime": runtime})),
            "output_sha256": _canonical_hash(stable),
            "read_only": True,
            "injection_performed": False,
        }
