"""Materialize compiler-accepted discovery hypotheses as pending RCA cases.

This adapter is intentionally offline.  It does not infer a weakness from a
discovery result, run an action, or call an LLM.  Every case starts at the
deterministic ``candidate/pending/none`` boundary and keeps the discovery
handoff as an auditable source artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.discovery_to_rca import build_case_from_hypothesis
from tools.project_onboarding import validate_project_profile
from tools.rca_loop import _contains_sensitive_value, sha256_json
from tools.sock_shop_pilot import attach_pilot_contract_to_case


SCHEMA_VERSION = "chaosatlas-rca-loop-v1"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if _contains_sensitive_value(text):
        raise ValueError(f"refusing to write sensitive values into {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _accepted_hypotheses(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    if handoff.get("status") != "handoff_ready":
        raise ValueError("discovery handoff must have status=handoff_ready")
    selected = handoff.get("selected_hypotheses")
    if not isinstance(selected, list) or not selected:
        raise ValueError("discovery handoff must contain non-empty accepted selected_hypotheses")
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(selected):
        if not isinstance(item, dict):
            raise ValueError(f"selected_hypotheses[{index}] must be an object")
        hid = str(item.get("hypothesis_id") or "").strip()
        if not hid:
            raise ValueError(f"selected_hypotheses[{index}] is missing hypothesis_id")
        if hid in seen_ids:
            raise ValueError(f"duplicate hypothesis_id: {hid}")
        seen_ids.add(hid)
        result.append(item)
    return result


def _business_oracle(profile: dict[str, Any], oracle_id: str | None) -> dict[str, str]:
    oracles = profile.get("business_oracles")
    if not isinstance(oracles, list) or not oracles:
        raise ValueError("profile must define at least one business oracle")
    selected = None
    for oracle in oracles:
        if not isinstance(oracle, dict):
            continue
        if oracle_id is None or str(oracle.get("id") or "") == oracle_id:
            selected = oracle
            break
    if selected is None:
        raise ValueError(f"unknown business oracle: {oracle_id}")
    workflow = str(selected.get("entrypoint") or "").strip()
    success = str(selected.get("success_contract") or "").strip()
    if not workflow or not success:
        raise ValueError("business oracle requires entrypoint and success_contract")
    return {"workflow": workflow, "success": success}


def build_rca_cases(
    handoff: dict[str, Any],
    *,
    profile: dict[str, Any],
    round_id: str,
    output_root: Path,
    oracle_id: str | None = None,
    pilot_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a fresh RCA input artifact from accepted discovery output."""

    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"output {output_root} already exists and is not empty")
    if not isinstance(handoff, dict):
        raise ValueError("handoff must be an object")
    if _contains_sensitive_value(json.dumps(handoff, ensure_ascii=True)):
        raise ValueError("discovery handoff contains sensitive values")
    schema = validate_project_profile(profile)
    if not schema["valid"]:
        raise ValueError("invalid project profile: " + "; ".join(schema["errors"]))
    normalized_profile = schema["profile"]
    project_id = str(normalized_profile.get("project_id") or "").strip()
    project_commit = str(normalized_profile.get("project_commit") or "").strip()
    round_id = str(round_id or "").strip()
    if not round_id:
        raise ValueError("round_id is required")

    hypotheses = _accepted_hypotheses(handoff)
    oracle = _business_oracle(normalized_profile, oracle_id)
    cases: list[dict[str, Any]] = []
    seen_weakness_ids: set[str] = set()
    for index, hypothesis in enumerate(hypotheses):
        declared_project = str(hypothesis.get("project_id") or "").strip()
        if declared_project != project_id:
            raise ValueError(
                f"selected_hypotheses[{index}] project_id {declared_project!r} "
                f"does not match profile project_id {project_id!r}"
            )
        declared_commit = hypothesis.get("project_commit")
        if declared_commit is not None and str(declared_commit).strip() != project_commit:
            raise ValueError(f"selected_hypotheses[{index}] project_commit does not match profile")
        case = build_case_from_hypothesis(
            hypothesis,
            project_id=project_id,
            project_commit=project_commit,
            round_id=round_id,
            business_oracle=oracle,
            namespace=str((normalized_profile.get("namespace_policy") or {}).get("allowed_namespaces", [""])[0]),
            source_ref="discovery/handoff.json",
        )
        if pilot_contract is not None:
            case = attach_pilot_contract_to_case(case, pilot_contract)
        if case["weakness_id"] in seen_weakness_ids:
            raise ValueError(f"duplicate weakness_id: {case['weakness_id']}")
        seen_weakness_ids.add(case["weakness_id"])
        cases.append(case)

    output_root.mkdir(parents=True, exist_ok=True)
    handoff_ref = "discovery/handoff.json"
    _write_json(output_root / handoff_ref, handoff)
    for case in cases:
        _write_json(output_root / "cases" / f"{case['weakness_id']}.json", case)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool": "build_rca_cases_from_discovery",
        "project_id": project_id,
        "project_commit": project_commit,
        "round_id": round_id,
        "input": {
            "discovery_source": handoff_ref,
            "discovery_sha256": sha256_json(handoff),
            "business_oracle_id": oracle_id or str((normalized_profile["business_oracles"] or [{}])[0].get("id") or ""),
            "pilot_contract_sha256": sha256_json(pilot_contract) if pilot_contract is not None else None,
        },
        "cases": [
            {"weakness_id": case["weakness_id"], "hypothesis_id": case["hypothesis_ids"][0]}
            for case in cases
        ],
        "knowledge_base_updated": False,
    }
    _write_json(output_root / "manifest.json", manifest)
    return {"status": "completed", "case_count": len(cases), "manifest": manifest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--oracle-id")
    parser.add_argument("--pilot-contract", type=Path)
    args = parser.parse_args(argv)
    result = build_rca_cases(
        _read_object(args.handoff),
        profile=_read_object(args.profile),
        round_id=args.round_id,
        output_root=args.output,
        oracle_id=args.oracle_id,
        pilot_contract=_read_object(args.pilot_contract) if args.pilot_contract else None,
    )
    print(json.dumps({"status": result["status"], "case_count": result["case_count"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
