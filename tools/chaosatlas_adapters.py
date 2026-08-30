"""Offline adapters for the first ChaosAtlas unified closed-loop milestone."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.build_deployment_capability_pool import build_pool
from tools.project_onboarding import validate_project_profile
from tools.recovery_contract import contract_for_fault
from tools.fault_catalog import implemented_fault_families


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class OfflineProjectAdapter:
    """Read-only project adapter backed by a frozen JSON facts file."""

    def __init__(self, facts_path: Path, *, workspace_root: Path) -> None:
        self.facts_path = Path(facts_path)
        self.workspace_root = Path(workspace_root).resolve()

    def _facts(self) -> dict[str, Any]:
        value = json.loads(self.facts_path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict) or value.get("schema_version") != "chaosatlas-offline-facts-v1":
            raise ValueError("offline facts must use chaosatlas-offline-facts-v1")
        return value

    def onboard(self, profile_path: Path, workspace_root: Path | None = None) -> dict[str, Any]:
        path = Path(profile_path)
        profile = json.loads(path.read_text(encoding="utf-8-sig"))
        checked = validate_project_profile(profile)
        if not checked["valid"]:
            return {"status": "method_invalid", "errors": checked["errors"], "profile": checked.get("profile", {})}
        facts = self._facts()
        if str(checked["profile"].get("project_id") or "").casefold() != str(facts.get("project_id") or "").casefold():
            return {"status": "method_invalid", "errors": ["profile/facts project_id mismatch"]}
        if checked["profile"].get("project_commit") != facts.get("project_commit"):
            return {"status": "method_invalid", "errors": ["profile/facts project_commit mismatch"]}
        return {
            "status": "ready_for_static_analysis",
            "profile": checked["profile"],
            "warnings": checked.get("warnings", []),
            "facts_sha256": _canonical_hash(facts),
            "claim_scope": "static",
        }

    def inventory(self, profile: dict[str, Any]) -> dict[str, Any]:
        facts = self._facts()
        if str(profile.get("project_id") or "").casefold() != str(facts.get("project_id") or "").casefold():
            raise ValueError("profile/facts project_id mismatch")
        services = [str(item) for item in facts.get("services") or []]
        deployments = [deepcopy(item) for item in facts.get("deployments") or [] if isinstance(item, dict)]
        dependencies = [deepcopy(item) for item in facts.get("dependencies") or [] if isinstance(item, dict)]
        oracles = [deepcopy(item) for item in (profile.get("business_oracles") or facts.get("business_oracles") or []) if isinstance(item, dict)]
        if not services or not deployments or not oracles:
            raise ValueError("offline facts require services, deployments and business_oracles")
        return {
            "schema_version": "chaosatlas-inventory-v1",
            "project_id": facts["project_id"],
            "project_commit": facts.get("project_commit"),
            "namespace": facts.get("namespace"),
            "services": services,
            "deployments": deployments,
            "dependencies": dependencies,
            "business_oracles": oracles,
            "facts_sha256": _canonical_hash(facts),
            "claim_scope": "static",
        }

    def detect_server_deployment(self, inventory: dict[str, Any]) -> dict[str, Any]:
        if str(inventory.get("project_id") or "").casefold() != str(self._facts().get("project_id") or "").casefold():
            return {"status": "method_invalid", "errors": ["inventory/facts project_id mismatch"], "candidates": []}
        facts = self._facts()
        source_pool: dict[str, Any] = {"status": "not_available"}
        manifest_root = facts.get("manifest_root")
        if manifest_root:
            root = (self.workspace_root / str(manifest_root)).resolve()
            if root == self.workspace_root or self.workspace_root not in root.parents:
                source_pool = {"status": "method_invalid", "reason": "manifest root escapes workspace"}
            elif root.exists():
                source_pool = build_pool(
                    root,
                    project_id=str(facts["project_id"]),
                    project_commit=str(facts.get("project_commit") or ""),
                    namespace=str(facts.get("namespace") or ""),
                )
        candidates: list[dict[str, Any]] = []
        for item in inventory.get("deployments") or []:
            name = str(item.get("name") or "")
            selector = {str(k): str(v) for k, v in (item.get("selector") or {}).items()}
            if not name or not selector:
                continue
            node_id = f"deployment:{inventory['project_id']}:{name}"
            candidates.append({
                "candidate_id": f"server:{node_id}",
                "node_id": node_id,
                "target": name,
                "target_kind": "deployment",
                "namespace": inventory.get("namespace"),
                "selector": selector,
                "desired_replicas": int(item.get("desired_replicas") or 0),
                "fault_families": list(implemented_fault_families()),
                "recovery_contract": {
                    "replacement_identity_required": True,
                    "ready_required": True,
                    "business_probe_required": True,
                    "cleanup_required": True,
                },
                "static_prior": "singleton_availability_risk" if int(item.get("desired_replicas") or 0) == 1 else None,
            })
        if not candidates:
            return {"status": "method_invalid", "errors": ["no valid deployment facts"], "candidates": [], "capability_name": "server_deployment_detection"}
        return {
            "schema_version": "chaosatlas-server-deployment-detection-v1",
            "status": "verified",
            "capability_name": "server_deployment_detection",
            "project_id": inventory["project_id"],
            "namespace": inventory.get("namespace"),
            "candidates": candidates,
            "impact_graph": [
                {"source": str(edge.get("source")), "target": str(edge.get("target")), "relation": str(edge.get("relation"))}
                for edge in inventory.get("dependencies") or []
            ],
            "source_pool_status": source_pool.get("status"),
            "source_pool_errors": source_pool.get("errors", []),
            "claim_scope": "static",
        }

    def map_test_nodes(self, detection: dict[str, Any]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for candidate in detection.get("candidates") or []:
            for family in candidate.get("fault_families") or []:
                item = deepcopy(candidate)
                item["candidate_id"] = f"{candidate['candidate_id']}:{family}"
                item["fault_family"] = family
                item["recovery_contract"] = contract_for_fault(candidate.get("recovery_contract"), family)
                item["test_node"] = {
                    "target": candidate.get("target"),
                    "target_kind": candidate.get("target_kind"),
                    "family": family,
                }
                candidates.append(item)
        return {
            "schema_version": "chaosatlas-candidate-space-v1",
            "status": "verified" if candidates else "method_invalid",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "claim_scope": "static",
        }


class KnowledgeProvider:
    """Read-only adapter for existing formal knowledge cards."""

    def retrieve(
        self,
        *,
        project_id: str,
        candidate_space: dict[str, Any],
        root: Path | None = None,
        project_commit: str | None = None,
    ) -> dict[str, Any]:
        cards: list[dict[str, Any]] = []
        rejected_cards: list[dict[str, Any]] = []
        if root is not None and Path(root).is_dir():
            for path in sorted(Path(root).glob("KB-*.json")):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    status = value.get("knowledge_status") or value.get("status")
                    if status in {"contested", "pending"}:
                        continue
                    card_project = value.get("project")
                    card_commit = value.get("project_commit")
                    if card_project != project_id:
                        rejected_cards.append({"id": value.get("id", path.stem), "reason": "project_mismatch", "project": card_project})
                        continue
                    if project_commit is not None and card_commit != project_commit:
                        rejected_cards.append({
                            "id": value.get("id", path.stem),
                            "reason": "project_identity_missing" if not card_commit else "project_commit_mismatch",
                            "project": card_project,
                            "project_commit": card_commit,
                        })
                        continue
                    cards.append({
                        "id": value.get("id", path.stem),
                        "schema_version": value.get("schema_version"),
                        "status": status,
                        "knowledge_status": status,
                        "project": value.get("project"),
                        "project_commit": value.get("project_commit"),
                        "classification": value.get("classification"),
                        "target": value.get("target"),
                        "target_kind": value.get("target_kind"),
                        "edge": value.get("edge"),
                        "weakness_id": value.get("weakness_id"),
                        "rca_status": value.get("rca_status"),
                        "test_node": value.get("test_node"),
                        "hypothesis": value.get("hypothesis"),
                        "root_cause": value.get("root_cause"),
                        "next_evidence": value.get("next_evidence") or [],
                    })
        return {
            "schema_version": "chaosatlas-retrieval-v1",
            "project_id": project_id,
            "candidate_count": int(candidate_space.get("candidate_count") or 0),
            "cards": cards,
            "rejected_cards": rejected_cards,
            "knowledge_status": "read_only",
            "claim_scope": "static",
        }


class FakeExecutor:
    """Deterministic lifecycle simulator; it cannot produce runtime claims."""

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(plan, dict) or not plan.get("candidate_id"):
            raise ValueError("fake execution plan requires candidate_id")
        return {
            "schema_version": "chaosatlas-fake-execution-v1",
            "candidate_id": plan["candidate_id"],
            "evidence_status": "synthetic",
            "claim_scope": "synthetic",
            "lifecycle": ["preflight", "baseline", "inject", "observe", "recover", "cleanup"],
            "injection_confirmed": False,
            "recovery_confirmed": True,
            "cleanup_confirmed": True,
            "runtime_verdict": "not_run",
            "observation": {"expected_invariant": plan.get("expected_invariant"), "status": "not_run"},
        }
