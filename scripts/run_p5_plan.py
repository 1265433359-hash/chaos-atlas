"""Build read-only P5 plans from external 32+9 capability evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    _root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_root / "src"))
    sys.path.insert(0, str(_root))

from chaosatlas.experiments.p5 import build_experiment_plan, build_p5_report


def _load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig").strip()
    # Historical evidence writers emitted a literal ``\\n`` after the JSON
    # document.  Accept it without weakening the object schema.
    if text.endswith(r"\n"):
        text = text[:-2].rstrip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-root", type=Path, required=True, help="external root containing <project>-41-capability-bootstrap.json")
    parser.add_argument("--output", type=Path, required=True, help="external output directory")
    parser.add_argument("--project", action="append", help="project id; repeat or omit for all four apps")
    args = parser.parse_args(argv)
    projects = args.project or ["immich", "medusa", "rocketchat", "erpnext"]
    args.output.mkdir(parents=True, exist_ok=True)
    plans = []
    for project_id in projects:
        bootstrap_path = args.bootstrap_root / f"{project_id}-41-capability-bootstrap.json"
        bootstrap = _load(bootstrap_path)
        plan = build_experiment_plan(
            project_id=project_id,
            project_revision=str(bootstrap.get("project_revision") or "unknown"),
            capability_bootstrap=bootstrap,
        )
        (args.output / f"{project_id}-experiment-plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        plans.append(plan)
    report = build_p5_report(plans=plans, real_evidence=False)
    (args.output / "p5-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "planned", "projects": len(plans), "output": str(args.output.resolve()), "real_evidence": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
