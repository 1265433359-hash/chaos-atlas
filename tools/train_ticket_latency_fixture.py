"""Read-only Train Ticket latency-boundary fixture for Phase 4 feedback tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.classify_runtime_result import classify
from tools.compile_rca_regression import compile_regression_intents


def _load(root: Path, name: str) -> dict[str, Any]:
    path = Path(root) / "runtime" / name
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"fixture artifact must be an object: {path}")
    return value


def build_train_ticket_latency_fixture(root: Path) -> dict[str, Any]:
    """Build a deterministic boundary fixture from frozen runtime evidence."""

    root = Path(root)
    boundary = _load(root, "generated_station_network_delay_boundary_comparison.json")
    baseline_success = _load(root, "baseline_station_success.json")
    baseline_not_found = _load(root, "baseline_station_not_found.json")
    r1 = _load(root, "generated_station_network_delay_runner_result.json")
    r4 = _load(root, "generated_station_network_delay_r4_runner_result.json")
    timeout_result = _load(root, "generated_station_network_delay_r4_result.json")
    profiles = list(boundary.get("profiles") or [])
    if len(profiles) != 3:
        raise ValueError("Train Ticket boundary fixture requires the 100ms/500ms/2s ladder")
    if not all(item.get("classification") == "response_preserved_latency_degradation" for item in profiles):
        raise ValueError("latency ladder must remain response-preserved degradation")
    normalized_boundary = dict(boundary.get("boundary") or {})
    evaluation_budget = timeout_result.get("evaluation_budget") or {}
    normalized_boundary["client_timeout_sec"] = float(
        evaluation_budget.get("client_timeout_sec", normalized_boundary.get("client_observation_timeout_sec", 0))
    )
    normalized_boundary["production_slo_defined"] = bool(evaluation_budget.get("production_slo_defined", False))
    if normalized_boundary["production_slo_defined"] is not False:
        raise ValueError("fixture requires an explicitly undefined production SLO")

    r1_classification = classify(r1, baseline_success)
    timeout_classification = classify(r4, baseline_not_found)
    if r1_classification.get("classification") != "response_preserved_latency_degradation":
        raise ValueError("r1 response-preserved classification drifted")
    if timeout_classification.get("classification") != "client_timeout_observed":
        raise ValueError("r4 timeout classification drifted")
    if timeout_result.get("interpretation", {}).get("classification") != "client_timeout_server_completion_after_delay":
        raise ValueError("server-completion-after-timeout evidence is missing")

    card = {
        "schema_version": "chaosatlas-train-ticket-latency-boundary-v1",
        "id": "KB-TT-LATENCY-BOUNDARY-001",
        "project": "FudanSELab/train-ticket",
        "project_commit": "313886e99befb94be6cd45f085c98e0019f59829",
        "claim_scope": "service:ts-station-service/network-edge",
        "case_family": "latency_boundary",
        "weakness_status": "bounded",
        "rca_status": "bounded",
        "knowledge_status": "provisional",
        "defense_claim_type": None,
        "mechanism_level": "client_server_boundary",
        "applicability_conditions": [
            "direct Station oracle reaches ts-station-service",
            "controlled outbound delay is injected and confirmed",
            "operator production SLO remains undefined",
        ],
        "exclusion_conditions": [
            "does not prove timeout, retry, fallback or circuit-breaker defense",
            "does not prove a production SLO",
            "packet-level dependency attribution is unavailable",
        ],
        "next_evidence": [
            "operator_defined_latency_slo",
            "effective_client_timeout_configuration",
            "retry_or_fallback_mechanism_evidence",
        ],
        "stop_rule": "stop after one timeout-boundary reproduction until an operator SLO is defined",
        "regression_recipe": {"oracle": "Station success and controlled not-found oracles"},
    }
    regression = compile_regression_intents(
        [card],
        snapshot={
            "project": card["project"],
            "project_commit": card["project_commit"],
            "claim_scope": card["claim_scope"],
            "boundary": normalized_boundary,
        },
    )
    return {
        "schema_version": "chaosatlas-train-ticket-latency-boundary-fixture-v1",
        "project_id": card["project"],
        "project_commit": card["project_commit"],
        "claim_scope": card["claim_scope"],
        "boundary": normalized_boundary,
        "profiles": profiles,
        "timeout_case": {
            "classification": timeout_result["interpretation"]["classification"],
            "client_classification": timeout_classification["classification"],
            "defense_claim_type": None,
            "server_completion_after_client_timeout": True,
            "mechanism_evidence": False,
        },
        "knowledge_card": card,
        "regression": regression,
    }
