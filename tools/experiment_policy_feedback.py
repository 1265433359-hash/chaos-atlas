"""Ingest deterministic runtime classifications into project-local policy state."""

from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tools.experiment_policy import update_candidate_state
    from tools.feedback_protocol import CLASSIFICATIONS, classify_outcome
    from tools.policy_calibration import record_policy_outcome
except ModuleNotFoundError:  # direct script invocation
    from experiment_policy import update_candidate_state
    from feedback_protocol import CLASSIFICATIONS, classify_outcome
    from policy_calibration import record_policy_outcome


_SHA256 = set("0123456789abcdef")


def _load_result(result_path: Path | dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    if isinstance(result_path, dict):
        return dict(result_path), None
    path = Path(result_path)
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("runtime result must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _verify_hash(value: Any, field: str) -> None:
    if value is None:
        return
    text = str(value)
    if len(text) != 64 or any(char not in _SHA256 for char in text.lower()):
        raise ValueError(f"{field} must be a lowercase SHA-256")


def ingest_runtime_result(
    state: dict[str, Any],
    result_path: Path | dict[str, Any],
    *,
    calibration: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one validated deterministic classification to a policy state.

    The static denominator is never modified.  A result must identify a known
    candidate, belong to the same project/commit, and carry the same policy
    input hash when one is supplied.  Candidate signatures are checked against
    the frozen candidate row when available.
    """
    result, file_hash = _load_result(result_path)
    if result.get("project_id") not in (None, state.get("project_id")):
        raise ValueError("project_id mismatch")
    if result.get("project_commit") not in (None, state.get("project_commit")):
        raise ValueError("project_commit mismatch")
    supplied_input_hash = result.get("policy_input_sha256", result.get("input_sha256"))
    if supplied_input_hash is not None and supplied_input_hash != state.get("input_sha256"):
        raise ValueError("policy input hash mismatch")
    _verify_hash(result.get("result_sha256"), "result_sha256")
    if file_hash and result.get("result_file_sha256") is not None and result["result_file_sha256"] != file_hash:
        raise ValueError("result file hash mismatch")

    candidate_id = str(result.get("candidate_id") or "")
    row = (state.get("candidate_states") or {}).get(candidate_id)
    if not row:
        raise ValueError(f"unknown candidate_id: {candidate_id}")
    expected_signature = row.get("canonical_signature")
    supplied_signature = result.get("canonical_signature")
    if expected_signature is not None and supplied_signature != expected_signature:
        raise ValueError("candidate signature mismatch")

    classification = str(result.get("classification") or "")
    if classification not in CLASSIFICATIONS:
        # A runtime artifact may omit the materialized label, but it must then
        # be classifiable by the independent deterministic protocol.
        classification = classify_outcome(result)
    if classification not in CLASSIFICATIONS:
        raise ValueError("unsupported deterministic classification")
    normalized = dict(result)
    normalized["classification"] = classification
    normalized.setdefault("result_sha256", file_hash)
    # The round controller marks incomplete, blocked, and dirty children as
    # ineligible.  They remain in the audit ledger but cannot alter a policy
    # posterior or calibration metric.
    if result.get("eligible") is False:
        return state
    updated = update_candidate_state(state, normalized)
    if calibration is not None:
        record_policy_outcome(calibration, decision or {}, normalized)
    return updated


def write_policy_state(state: dict[str, Any], path: Path) -> None:
    """Atomically persist a policy state artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    updated = ingest_runtime_result(state, args.result)
    output = args.output or args.state
    write_policy_state(updated, output)
    print(json.dumps({"candidate_id": json.loads(args.result.read_text(encoding="utf-8")).get("candidate_id"), "output": str(output)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
