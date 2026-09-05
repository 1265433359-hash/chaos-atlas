"""Sock Shop adapter for the automated RCA loop.

Reads the frozen execution verdicts plus archived static manifests and compiles
the three pilot RCA case families defined in the 2026-08-20 design:

1. ``single_replica_podkill``    - deployment-availability weakness (no redundancy)
2. ``catalogue_db_podkill``      - competing database vs propagation hypotheses
3. ``http_abort_propagation``    - service-boundary transport error propagation

The tool is offline-only: it never calls kubectl, Docker, an LLM or the network,
and it writes only into an explicitly provided (empty or new) output directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.rca_loop import (
    _contains_sensitive_value,
    build_weakness_id,
    canonical_json,
    evaluate_rca_transition,
    make_evidence,
    plan_next_action,
    sha256_json,
)

SCHEMA_VERSION = "chaosatlas-rca-loop-v1"
VERDICT_RELATIVE = "artifacts/sock-shop/sock_shop_verdicts.json"
FROZEN_COLLECTED_AT = "2026-08-09T00:00:00Z"

_CASE_FAMILY_ORDER = (
    "single_replica_podkill",
    "catalogue_db_podkill",
    "http_abort_propagation",
)


def _frozen_evidence(**kwargs: Any) -> dict[str, Any]:
    evidence = make_evidence(**kwargs)
    evidence["collected_at"] = FROZEN_COLLECTED_AT
    return evidence


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=False) + "\n"
    if _contains_sensitive_value(text):
        raise ValueError(f"refusing to write sensitive values into {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _candidate(verdicts: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in verdicts.get("candidates", []):
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    raise ValueError(f"candidate {candidate_id} not found in verdict file")


def _availability_verdict(verdicts: dict[str, Any], service: str) -> dict[str, Any]:
    for entry in verdicts.get("availability_layer", {}).get("verdicts", []):
        if entry.get("service") == service:
            return entry
    raise ValueError(f"availability verdict for {service} not found in verdict file")


def _base_case(
    *,
    case_family: str,
    weakness_id: str,
    round_id: str,
    project_commit: str,
    test_node: dict[str, Any],
    symptom: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    boundary_confirmed: bool,
) -> dict[str, Any]:
    case = {
        "schema_version": "chaosatlas-weakness-case-v1",
        "case_family": case_family,
        "weakness_id": weakness_id,
        "project_id": "sock-shop",
        "project_commit": project_commit,
        "round_id": round_id,
        "test_node": test_node,
        "symptom": symptom,
        "weakness_status": "confirmed",
        "rca_status": "pending",
        "knowledge_status": "provisional",
        "evidence_refs": evidence_refs,
        "hypothesis_ids": [],
        "next_actions": [],
        "replicates": [],
        "rca_audit": [],
    }
    supports = sum(1 for ev in evidence_refs if ev["polarity"] == "supports")
    transition = evaluate_rca_transition(
        current="pending",
        target="bounded",
        boundary_confirmed=boundary_confirmed,
        supporting_evidence=supports,
        required_evidence_complete=False,
        discriminating_action=False,
        high_severity_contradiction=False,
    )
    if not transition["allowed"]:
        raise ValueError(f"case {weakness_id} could not reach bounded: {transition}")
    case["rca_status"] = transition["next_status"]
    case["rca_audit"].append(transition)
    return case


def _single_replica_case(verdicts: dict[str, Any], project_commit: str, round_id: str) -> dict[str, Any]:
    runtime = _availability_verdict(verdicts, "front-end")
    evidence = [
        _frozen_evidence(
            evidence_id="EV-SS-SINGLETON-MANIFEST-001",
            kind="manifest",
            polarity="supports",
            claim_scope="front-end deployment redundancy",
            source_ref="artifacts/sock-shop/sock-shop-lab-manifest.yaml",
            interpretation=(
                "static manifest shows the front-end deployment runs a single replica "
                "with no pod disruption budget, so there is no redundancy to absorb a pod kill"
            ),
        ),
        _frozen_evidence(
            evidence_id="EV-SS-SINGLETON-READY-001",
            kind="runtime_log",
            polarity="supports",
            claim_scope="front-end deployment redundancy",
            source_ref="artifacts/sock-shop/avail_frontend_kill.json",
            interpretation=(
                "pod-kill moved Ready 1->0 for the whole replacement window, confirming "
                "the singleton deployment loses all capacity until a new pod is ready"
            ),
        ),
        _frozen_evidence(
            evidence_id="EV-SS-SINGLETON-COUNTERFACTUAL-001",
            kind="counterfactual",
            polarity="unavailable",
            claim_scope="front-end deployment redundancy",
            source_ref="artifacts/sock-shop/sock_availability_layer_verified.md",
            interpretation=(
                "no replicas>1 counterfactual exists in the archived evidence because the "
                "lab had no multi-replica service; recorded as unavailable, not as refutation"
            ),
        ),
    ]
    return _base_case(
        case_family="single_replica_podkill",
        weakness_id=build_weakness_id("sock-shop", "front-end", "PodChaos", "pod-kill"),
        round_id=round_id,
        project_commit=project_commit,
        test_node={
            "family": "PodChaos",
            "operation": "pod-kill",
            "target_role": "front-end deployment",
            "source_ref": "artifacts/sock-shop/avail_frontend_kill.json",
        },
        symptom={
            "oracle": "deployment availability (Ready replicas)",
            "baseline_contract": "1/1 ready replicas, service available",
            "injected_contract": "0/1 ready replicas, total outage during replacement window",
            "observed_change": f"ready drop for {runtime.get('outage_window_s')}s during pod kill",
        },
        evidence_refs=evidence,
        boundary_confirmed=True,
    )


def _catalogue_db_case(verdicts: dict[str, Any], project_commit: str, round_id: str) -> dict[str, Any]:
    evidence = [
        _frozen_evidence(
            evidence_id="EV-SS-CATDB-MANIFEST-001",
            kind="manifest",
            polarity="supports",
            claim_scope="catalogue-db dependency boundary",
            source_ref="artifacts/sock-shop/catalogue-db-reset.yaml",
            interpretation=(
                "catalogue-db is a single-replica deployment that the catalogue service "
                "depends on; killing it removes the entire database dependency at once"
            ),
        ),
        _frozen_evidence(
            evidence_id="EV-SS-CATDB-LOGS-001",
            kind="runtime_log",
            polarity="unavailable",
            claim_scope="catalogue-db dependency boundary",
            source_ref="artifacts/sock-shop/sock_availability_layer_verified.md",
            interpretation=(
                "no scoped catalogue pod log linking connection failures to request errors "
                "was captured during the catalogue-db disruption; recorded as unavailable"
            ),
        ),
        _frozen_evidence(
            evidence_id="EV-SS-CATDB-SOURCE-001",
            kind="source_span",
            polarity="unavailable",
            claim_scope="catalogue-db dependency boundary",
            source_ref="artifacts/sock-shop/sock_shop_verdicts.json",
            interpretation=(
                "no source-level mapping of catalogue database connection handling was "
                "archived for this boundary; recorded as unavailable"
            ),
        ),
    ]
    return _base_case(
        case_family="catalogue_db_podkill",
        weakness_id=build_weakness_id("sock-shop", "catalogue->catalogue-db", "PodChaos", "pod-kill"),
        round_id=round_id,
        project_commit=project_commit,
        test_node={
            "family": "PodChaos",
            "operation": "pod-kill",
            "target_role": "catalogue-db deployment",
            "source_ref": "artifacts/sock-shop/catalogue-db-reset.yaml",
        },
        symptom={
            "oracle": "catalogue business path",
            "baseline_contract": "catalogue requests served from the database",
            "injected_contract": "database dependency removed while pod is down",
            "observed_change": "business dependency on a single database instance is exposed during kill",
        },
        evidence_refs=evidence,
        boundary_confirmed=True,
    )


def _http_abort_case(verdicts: dict[str, Any], project_commit: str, round_id: str) -> dict[str, Any]:
    candidate = _candidate(verdicts, "SOCK-FRONTEND-CATALOGUE-LOSS-100")
    edge = candidate.get("edge", "front-end->catalogue")
    evidence = [
        _frozen_evidence(
            evidence_id="EV-SS-ABORT-DIRECT-001",
            kind="oracle",
            polarity="supports",
            claim_scope=edge,
            source_ref=VERDICT_RELATIVE,
            interpretation=(
                "direct dependency measurement shows the abort at this edge changes the "
                "response contract from the baseline behaviour for the full abort window"
            ),
        ),
        _frozen_evidence(
            evidence_id="EV-SS-ABORT-REALPATH-001",
            kind="business_path_replay",
            polarity="unavailable",
            claim_scope=edge,
            source_ref=VERDICT_RELATIVE,
            interpretation=(
                "real business path replay for this abort edge was not archived, so the "
                "propagation claim stays at the measured service boundary; unavailable "
                "evidence must not be read as timeout-configuration proof"
            ),
        ),
    ]
    return _base_case(
        case_family="http_abort_propagation",
        weakness_id=build_weakness_id("sock-shop", edge, "HTTPChaos", "abort"),
        round_id=round_id,
        project_commit=project_commit,
        test_node={
            "family": "HTTPChaos",
            "operation": "abort",
            "target_role": edge,
            "source_ref": VERDICT_RELATIVE,
        },
        symptom={
            "oracle": "edge response contract",
            "baseline_contract": str(candidate.get("baseline", "")),
            "injected_contract": str(candidate.get("injected", "")),
            "observed_change": "response contract changed while the abort was active",
        },
        evidence_refs=evidence,
        boundary_confirmed=True,
    )


def hypotheses_for_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the fixed hypothesis templates selected by ``case_family``."""

    family = case.get("case_family")
    weakness_id = case.get("weakness_id", "")
    edge = case.get("test_node", {}).get("target_role", "")

    if family == "single_replica_podkill":
        templates = [
            {
                "claim": "the front-end workload is a singleton with no redundancy, so any pod kill produces a full-outage window",
                "mechanism_class": "singleton_workload_no_redundancy",
                "mechanism_level": "deployment",
                "expected_observations": [
                    "manifest shows replicas=1 and no pod disruption budget",
                    "Ready drops to zero for the whole replacement window on kill",
                    "business requests fail during the same window",
                ],
                "falsifiers": [
                    "a second ready replica absorbs the kill with no outage",
                    "a pod disruption budget keeps capacity during the kill",
                ],
                "required_evidence": [
                    "static_manifest_replica_facts",
                    "ready_transition_runtime",
                    "business_impact_in_window",
                ],
                "evidence_for": ["EV-SS-SINGLETON-MANIFEST-001", "EV-SS-SINGLETON-READY-001"],
                "evidence_against": [],
            }
        ]
    elif family == "catalogue_db_podkill":
        templates = [
            {
                "claim": "catalogue requests fail because the database connection itself is unavailable while catalogue-db is down",
                "mechanism_class": "database_connection_unavailable",
                "mechanism_level": "dependency",
                "expected_observations": [
                    "catalogue logs show connection or pool failures in the kill window",
                    "request errors start and end with the database availability window",
                ],
                "falsifiers": [
                    "catalogue keeps serving cached data during the kill window",
                    "request errors persist after the database is reachable again",
                ],
                "required_evidence": [
                    "scoped_catalogue_logs",
                    "connection_failure_to_request_error_link",
                ],
                "evidence_for": ["EV-SS-CATDB-MANIFEST-001"],
                "evidence_against": [],
            },
            {
                "claim": "catalogue fails because it propagates database errors into its own error responses without an isolating fallback",
                "mechanism_class": "catalogue_error_propagation",
                "mechanism_level": "service_internal",
                "expected_observations": [
                    "catalogue returns explicit error responses tied to downstream database failures",
                    "source or config shows no fallback or circuit breaker for the database call",
                ],
                "falsifiers": [
                    "catalogue returns a fallback contract while the database is down",
                    "errors only appear after an internal timeout unrelated to database state",
                ],
                "required_evidence": [
                    "source_or_config_mapping",
                    "discriminating_replay",
                ],
                "evidence_for": [],
                "evidence_against": [],
            },
        ]
    elif family == "http_abort_propagation":
        templates = [
            {
                "claim": "transport abort at the edge is propagated into the business response at the service boundary",
                "mechanism_class": "transport_error_propagation",
                "mechanism_level": "service_boundary",
                "expected_observations": [
                    "the edge response contract changes while the abort is active",
                    "the caller observes the propagated failure rather than a fallback",
                ],
                "falsifiers": [
                    "a verified fallback returns the original business contract during the abort",
                    "the same symptom appears with no corresponding downstream abort",
                ],
                "required_evidence": [
                    "runtime_business_path",
                    "downstream_diagnostic_or_source_mapping",
                    "recovery_after_fault_removal",
                ],
                "evidence_for": ["EV-SS-ABORT-DIRECT-001"],
                "evidence_against": [],
                "claim_boundary": (
                    "the claim is limited to propagation at the measured service boundary; "
                    "it must NOT be promoted to a timeout-configuration mechanism without "
                    "source or config evidence"
                ),
            },
        ]
    elif str(family or "").startswith("native_"):
        native_hypotheses = case.get("hypotheses")
        if not isinstance(native_hypotheses, list) or not native_hypotheses:
            raise ValueError(f"native case_family requires hypotheses: {family}")
        templates = [dict(item) for item in native_hypotheses if isinstance(item, dict)]
        if len(templates) != len(native_hypotheses):
            raise ValueError(f"native case_family hypotheses must be objects: {family}")
    else:
        raise ValueError(f"unknown case_family: {family}")

    hypotheses = []
    for index, template in enumerate(templates, 1):
        hypothesis = {
            "hypothesis_id": f"RCA-{weakness_id}-{index:02d}",
            "weakness_id": weakness_id,
            "scope": {"services": edge.split("->") if "->" in edge else [edge], "edge": edge},
            "unsupported_claims": [],
            "status": "pending",
            "confidence": 0.0,
            "next_action": None,
        }
        hypothesis.update(template)
        if family == "single_replica_podkill":
            # manifest + ready-transition evidence is direct, so the deployment-level
            # claim is supported; only the counterfactual remains open.
            hypothesis["unsupported_claims"] = ["isolated_scale_to_two_counterfactual"]
            hypothesis["status"] = "bounded"
        else:
            # competing/unarchived mechanisms: nothing beyond the boundary is proven yet
            hypothesis["unsupported_claims"] = list(hypothesis["required_evidence"])
        hypotheses.append(hypothesis)
    return hypotheses


def _with_execution_context(
    case: dict[str, Any],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    snapshot = {
        "project_id": case.get("project_id"),
        "project_commit": case.get("project_commit"),
        "weakness_id": case.get("weakness_id"),
        "test_node": case.get("test_node"),
        "symptom": case.get("symptom"),
    }
    snapshot_sha256 = sha256_json(snapshot)
    baseline_contract = str((case.get("symptom") or {}).get("baseline_contract") or "")
    enriched: list[dict[str, Any]] = []
    for action in actions:
        item = dict(action)
        item.update(
            {
                "namespace": str(case.get("namespace") or "chaosatlas-sock-shop"),
                "project_snapshot_sha256": snapshot_sha256,
                "baseline_contract": baseline_contract,
                "budget": {
                    "max_seconds": 60 if item.get("kind") in {"business_replay", "isolated_counterfactual"} else 30,
                    "max_retries": 0,
                },
                "cleanup_contract": list(item.get("cleanup") or []),
            }
        )
        enriched.append(item)
    return enriched


def actions_for_case(
    case: dict[str, Any], hypotheses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return safe, schema-complete evidence actions for the live hypotheses."""

    family = case.get("case_family")
    if family == "single_replica_podkill":
        return _with_execution_context(case, [
            {
                "action_id": "A-SS-SINGLETON-CONFIG-001",
                "kind": "config_lookup",
                "target_scope": "front-end deployment",
                "hypotheses_separated": 1,
                "evidence_gain": 2,
                "cost": 0,
                "risk": 0,
                "environment_uncertainty": 0,
                "preconditions": ["frozen_manifest"],
                "cleanup": ["none"],
                "output_schema": "manifest_facts",
                "stop_conditions": ["manifest replica facts already recorded"],
            },
            {
                "action_id": "A-SS-SINGLETON-READY-001",
                "kind": "log_lookup",
                "target_scope": "front-end deployment",
                "hypotheses_separated": 1,
                "evidence_gain": 2,
                "cost": 1,
                "risk": 0,
                "environment_uncertainty": 0,
                "preconditions": ["captured_ready_samples"],
                "cleanup": ["none"],
                "output_schema": "runtime_log",
                "stop_conditions": ["window already captured in avail_frontend_kill.json"],
            },
            {
                "action_id": "A-SS-SINGLETON-COUNTERFACTUAL-001",
                "kind": "isolated_counterfactual",
                "target_scope": "front-end deployment",
                "hypotheses_separated": 1,
                "evidence_gain": 3,
                "cost": 2,
                "risk": 1,
                "environment_uncertainty": 1,
                "preconditions": ["runner_allows_replica_scaling"],
                "cleanup": ["scale_back_to_one", "washout_verification"],
                "output_schema": "counterfactual_runtime",
                "stop_conditions": [
                    "abort when the runner refuses replica changes",
                    "abort after one bounded kill with full recovery",
                ],
            },
        ])
    if family == "catalogue_db_podkill":
        return _with_execution_context(case, [
            {
                "action_id": "A-SS-CATDB-CONFIG-001",
                "kind": "config_lookup",
                "target_scope": "catalogue-db deployment",
                "hypotheses_separated": 1,
                "evidence_gain": 2,
                "cost": 0,
                "risk": 0,
                "environment_uncertainty": 0,
                "preconditions": ["frozen_manifest"],
                "cleanup": ["none"],
                "output_schema": "manifest_facts",
                "stop_conditions": ["configuration facts already recorded"],
            },
            {
                "action_id": "A-SS-CATDB-LOGS-001",
                "kind": "log_lookup",
                "target_scope": "catalogue-db deployment",
                "hypotheses_separated": 2,
                "evidence_gain": 3,
                "cost": 1,
                "risk": 0,
                "environment_uncertainty": 1,
                "preconditions": ["captured_catalogue_logs"],
                "cleanup": ["none"],
                "output_schema": "runtime_log",
                "stop_conditions": [
                    "stop once connection failures are linked (or shown absent) to request errors",
                ],
            },
            {
                "action_id": "A-SS-CATDB-REPLAY-001",
                "kind": "business_replay",
                "target_scope": "catalogue-db deployment",
                "hypotheses_separated": 2,
                "evidence_gain": 3,
                "cost": 2,
                "risk": 1,
                "environment_uncertainty": 1,
                "preconditions": ["business_oracle_available", "runner_allows_bounded_kill"],
                "cleanup": ["washout_verification", "recovery_check"],
                "output_schema": "counterfactual_runtime",
                "stop_conditions": [
                    "stop after one replay with full recovery",
                    "abort when the oracle is unavailable",
                ],
            },
        ])
    if family == "http_abort_propagation":
        return _with_execution_context(case, [
            {
                "action_id": "A-SS-ABORT-CONFIG-001",
                "kind": "config_lookup",
                "target_scope": "front-end->catalogue",
                "hypotheses_separated": 1,
                "evidence_gain": 2,
                "cost": 0,
                "risk": 0,
                "environment_uncertainty": 0,
                "preconditions": ["frozen_manifest"],
                "cleanup": ["none"],
                "output_schema": "config_facts",
                "stop_conditions": [
                    "stop when timeout configuration is either found or confirmed absent",
                ],
            },
            {
                "action_id": "A-SS-ABORT-LOGS-001",
                "kind": "log_lookup",
                "target_scope": "front-end->catalogue",
                "hypotheses_separated": 1,
                "evidence_gain": 2,
                "cost": 1,
                "risk": 0,
                "environment_uncertainty": 0,
                "preconditions": ["captured_window"],
                "cleanup": ["none"],
                "output_schema": "runtime_log",
                "stop_conditions": ["window already captured"],
            },
            {
                "action_id": "A-SS-ABORT-REALPATH-001",
                "kind": "business_replay",
                "target_scope": "front-end->catalogue",
                "hypotheses_separated": 1,
                "evidence_gain": 3,
                "cost": 2,
                "risk": 1,
                "environment_uncertainty": 1,
                "preconditions": ["business_oracle_available"],
                "cleanup": ["washout_verification", "recovery_check"],
                "output_schema": "runtime",
                "stop_conditions": [
                    "stop after three valid reproductions or one clean falsification",
                    "abort when the real business path cannot be exercised",
                ],
                },
            ])
    if str(family or "").startswith("native_"):
        target_scope = str(
            (case.get("test_node") or {}).get("target")
            or (case.get("test_node") or {}).get("target_role")
            or "native target"
        )
        action_suffix = re.sub(r"[^A-Za-z0-9]+", "-", target_scope).strip("-").upper() or "TARGET"
        actions = [
            {
                "action_id": f"A-NATIVE-{action_suffix}-CONFIG-001",
                "kind": "config_lookup",
                "target_scope": target_scope,
                "hypotheses_separated": max(1, len(hypotheses)),
                "evidence_gain": 2,
                "cost": 0,
                "risk": 0,
                "environment_uncertainty": 0,
                "preconditions": ["frozen_manifest"],
                "cleanup": ["none"],
                "output_schema": "config_facts",
                "stop_conditions": ["frozen deployment facts are recorded"],
            },
            {
                "action_id": f"A-NATIVE-{action_suffix}-LOGS-001",
                "kind": "log_lookup",
                "target_scope": target_scope,
                "workload": target_scope.replace(":", "/", 1),
                "hypotheses_separated": max(1, len(hypotheses)),
                "evidence_gain": 3,
                "cost": 1,
                "risk": 0,
                "environment_uncertainty": 1,
                "preconditions": ["captured_window"],
                "cleanup": ["none"],
                "output_schema": "runtime_log",
                "stop_conditions": ["bounded log window is captured"],
            },
            {
                "action_id": f"A-NATIVE-{action_suffix}-EVENTS-001",
                "kind": "event_lookup",
                "target_scope": target_scope,
                "hypotheses_separated": max(1, len(hypotheses)),
                "evidence_gain": 2,
                "cost": 1,
                "risk": 0,
                "environment_uncertainty": 1,
                "preconditions": ["captured_window"],
                "cleanup": ["none"],
                "output_schema": "kubernetes_events",
                "stop_conditions": ["bounded event window is captured"],
            },
            {
                "action_id": f"A-NATIVE-{action_suffix}-INJECT-001",
                "kind": "native_fault_injection",
                "target_scope": target_scope,
                "hypotheses_separated": max(1, len(hypotheses)),
                "evidence_gain": 4,
                "cost": 3,
                "risk": 2,
                "environment_uncertainty": 2,
                "preconditions": ["native_executor_ready", "business_oracle_available"],
                "cleanup": ["remove_mutation", "recovery_check", "washout_verification"],
                "output_schema": "native_runtime_result",
                "stop_conditions": [
                    "stop when injection confirmation is unavailable",
                    "stop after recovery deadline or cleanup failure",
                ],
            },
        ]
        mutation_manifest = (case.get("test_node") or {}).get("mutation_manifest")
        if isinstance(mutation_manifest, dict):
            actions[1]["mutation_manifest"] = mutation_manifest
        return _with_execution_context(case, actions)
    raise ValueError(f"unknown case_family: {family}")


_AVAILABLE_PRECONDITIONS = {
    "frozen_verdicts",
    "frozen_manifest",
    "captured_ready_samples",
    "captured_window",
}


def build_sock_shop_pilot(
    *,
    verdict_path: Path,
    output_root: Path,
    project_commit: str,
    round_id: str,
) -> dict[str, Any]:
    """Read frozen verdicts, build cases/hypotheses/actions, and write output_root."""

    verdict_path = Path(verdict_path)
    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(
            f"output root {output_root} already exists and is not empty; refusing to overwrite"
        )
    verdicts = json.loads(verdict_path.read_text(encoding="utf-8"))
    if not isinstance(verdicts, dict):
        raise ValueError("verdict file must contain a JSON object")

    builders = {
        "single_replica_podkill": _single_replica_case,
        "catalogue_db_podkill": _catalogue_db_case,
        "http_abort_propagation": _http_abort_case,
    }
    cases = [
        builder(verdicts, project_commit, round_id) for builder in builders.values()
    ]
    case_plans = []
    for case in cases:
        hypotheses = hypotheses_for_case(case)
        actions = actions_for_case(case, hypotheses)
        plan = plan_next_action(actions, available_preconditions=_AVAILABLE_PRECONDITIONS)
        case["hypothesis_ids"] = [hyp["hypothesis_id"] for hyp in hypotheses]
        case["next_actions"] = [plan]
        for hypothesis in hypotheses:
            if hypothesis["status"] == "pending":
                hypothesis["next_action"] = plan["selected"]["action_id"] if plan["status"] == "planned" else None
            else:
                hypothesis["next_action"] = plan["selected"]["action_id"] if plan["status"] == "planned" else None
        case["hypotheses"] = hypotheses
        case_plans.append(
            {
                "weakness_id": case["weakness_id"],
                "case_family": case["case_family"],
                "plan": plan,
            }
        )
        hypothesis_path = output_root / "hypotheses"
        for hypothesis in hypotheses:
            _write_json(hypothesis_path / f"{hypothesis['hypothesis_id']}.json", hypothesis)
        _write_json(output_root / "cases" / f"{case['weakness_id']}.json", case)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool": "sock_shop_rca",
        "project_id": "sock-shop",
        "project_commit": project_commit,
        "round_id": round_id,
        "input": {
            "verdict_path": VERDICT_RELATIVE,
            "verdict_sha256": sha256_json(verdicts),
        },
        "cases": cases,
        "case_index": [
            {
                "weakness_id": case["weakness_id"],
                "case_family": case["case_family"],
                "weakness_status": case["weakness_status"],
                "rca_status": case["rca_status"],
                "knowledge_status": case["knowledge_status"],
                "next_action": case["next_actions"][0].get("selected", {}).get("action_id"),
                "unmet_gates": ["required_evidence_incomplete", "discriminating_action_required"],
            }
            for case in cases
        ],
        "knowledge_base_updated": False,
    }
    action_plan = {
        "schema_version": SCHEMA_VERSION,
        "tool": "sock_shop_rca",
        "round_id": round_id,
        "available_preconditions": sorted(_AVAILABLE_PRECONDITIONS),
        "case_plans": case_plans,
    }
    _write_json(output_root / "action_plan.json", action_plan)
    _write_json(output_root / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verdict", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-commit", required=True)
    parser.add_argument("--round-id", required=True)
    args = parser.parse_args(argv)
    manifest = build_sock_shop_pilot(
        verdict_path=args.verdict,
        output_root=args.output,
        project_commit=args.project_commit,
        round_id=args.round_id,
    )
    print(canonical_json(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
