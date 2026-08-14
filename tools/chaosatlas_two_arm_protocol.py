"""Deterministic contract for the three-project two-arm experiment."""

from __future__ import annotations

import hashlib
import json
from typing import Any


PROJECTS = ("online-boutique", "opentelemetry-demo", "sock-shop")
METHODS = ("ChaosAtlas-full", "ChaosAtlas-ablation")
SEEDS = (1001, 1002, 1003)
MAX_HYPOTHESES = 8
MAX_EXECUTED_HYPOTHESES = 4
REPETITIONS = 2
MAX_RUNTIME_UNITS = len(PROJECTS) * len(METHODS) * len(SEEDS) * MAX_EXECUTED_HYPOTHESES * REPETITIONS


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def validate_matrix_entry(project_id: str, method_id: str, seed: int) -> None:
    if project_id not in PROJECTS:
        raise ValueError(f"unknown project: {project_id}")
    if method_id not in METHODS:
        raise ValueError(f"unknown method: {method_id}")
    if seed not in SEEDS:
        raise ValueError(f"seed is not registered: {seed}")


def enumerate_matrix() -> list[dict[str, Any]]:
    return [
        {
            "project_id": project,
            "method_id": method,
            "seed": seed,
            "max_hypotheses": MAX_HYPOTHESES,
            "max_executed_hypotheses": MAX_EXECUTED_HYPOTHESES,
            "repetitions": REPETITIONS,
        }
        for project in PROJECTS
        for method in METHODS
        for seed in SEEDS
    ]


def pair_input_hashes(full_bundle: dict[str, Any], ablation_bundle: dict[str, Any]) -> dict[str, Any]:
    full_common = full_bundle.get("common_input")
    ablation_common = ablation_bundle.get("common_input")
    if full_common != ablation_common:
        raise ValueError("common input must be byte-identical between methods")
    if not full_bundle.get("knowledge_view"):
        raise ValueError("full bundle knowledge view is missing")
    if ablation_bundle.get("knowledge_view") is not None:
        raise ValueError("ablation bundle must not contain a knowledge view")
    return {
        "common_equal": True,
        "common_sha256": canonical_sha256(full_common),
        "full_knowledge_sha256": canonical_sha256(full_bundle["knowledge_view"]),
        "ablation_knowledge_sha256": None,
    }


def select_execution_hypotheses(hypotheses: list[dict[str, Any]]) -> dict[str, Any]:
    if len(hypotheses) > MAX_HYPOTHESES:
        raise ValueError(f"at most {MAX_HYPOTHESES} hypotheses may be generated")
    accepted = [item for item in hypotheses if item.get("compile_status") == "accepted"]
    rejected = [str(item.get("hypothesis_id", "")) for item in hypotheses if item.get("compile_status") != "accepted"]
    selected = accepted[:MAX_EXECUTED_HYPOTHESES]
    budget_not_executed = [str(item.get("hypothesis_id", "")) for item in accepted[MAX_EXECUTED_HYPOTHESES:]]
    return {
        "selected": selected,
        "rejected": rejected,
        "budget_not_executed": budget_not_executed,
        "repetitions": REPETITIONS,
    }


def classify_runtime_unit(*, baseline: bool, injection: bool, observation: bool, recovery: bool, cleanup: bool, independent_oracle: bool, repetitions_valid: int, environment_blocked: bool = False, method_invalid: bool = False) -> str:
    if method_invalid:
        return "method_invalid"
    if environment_blocked:
        return "environment_blocked"
    if repetitions_valid >= REPETITIONS and all((baseline, injection, observation, recovery, cleanup, independent_oracle)):
        return "confirmed_weakness"
    return "unsupported"
