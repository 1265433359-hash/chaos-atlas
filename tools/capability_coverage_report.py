"""Report native deployment capability coverage separately from CE validation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_NATIVE_CELLS = ("deployment_model", "hypothesis_generation", "scenario_compilation", "fault_execution", "ce_steady_state", "native_recovery", "attribution", "improvement_retest")
VALID = {"verified", "static_only", "blocked", "not_run"}


def _cells(values: dict[str, Any] | None, names: tuple[str, ...]) -> list[dict[str, Any]]:
    values = values or {}
    return [{"cell": name, "status": str(values.get(name, "not_run")) if str(values.get(name, "not_run")) in VALID else "not_run"} for name in names]


def build_report(native_cells: dict[str, Any] | None, ce_cells: dict[str, Any] | None = None, *, profile: str = "chaosatlas-native-deployment") -> dict[str, Any]:
    native = _cells(native_cells, REQUIRED_NATIVE_CELLS)
    ce_names = tuple((ce_cells or {}).keys()) or ("input_parity", "execution", "recovery", "attribution")
    ce = _cells(ce_cells, ce_names)
    claim = "full_native_capability" if all(item["status"] == "verified" for item in native) else "partial_capability_coverage"
    return {"schema_version": 1, "tool": "chaosatlas_capability_coverage", "profile": profile, "generated_at": datetime.now(timezone.utc).isoformat(), "native_capability_coverage": {"cells": native, "claim": claim}, "ce_profile_validation": {"cells": ce, "claim": "external_validation_only"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = build_report(payload.get("native_cells"), payload.get("ce_cells"), profile=str(payload.get("profile", "chaosatlas-native-deployment")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"claim": report["native_capability_coverage"]["claim"], "output": str(args.output)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

