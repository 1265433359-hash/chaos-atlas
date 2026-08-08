"""Backfill the defense-pattern library from M5 dual-track LLM attributions.

For every candidate the LLM judged 'defended' (with evidence), extract its
defense_mechanism family and add a pattern entry if one does not already
exist. This grows the library from hand-curated v1 seeds to evidence-driven
entries. LLM attributions are priors: each backfilled entry carries
confidence + the evidence files so a human (or later behavior evidence) can
verify or revoke it.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "artifacts" / "experiments" / "execution"
LIBRARY_PATH = ROOT / "artifacts" / "experiments" / "defense_pattern_library.json"


def load_library(path: Path = LIBRARY_PATH) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "patterns": []}


def save_library(library: dict[str, Any], path: Path = LIBRARY_PATH) -> None:
    path.write_text(json.dumps(library, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def backfill(results_path: Path, library_path: Path = LIBRARY_PATH) -> dict[str, Any]:
    results = json.loads(results_path.read_text(encoding="utf-8"))
    library = load_library(library_path)
    existing_ids = {p["pattern_id"] for p in library.get("patterns", [])}
    added: list[str] = []

    for r in results.get("results", []):
        # Only defended truths and only evidence-mode attributions (blind mode
        # has no runtime evidence, its mechanism is a guess).
        if r.get("truth") != "defended":
            continue
        evidence = r.get("evidence") or {}
        mechanism_text = evidence.get("defense_mechanism") or ""
        if not mechanism_text or mechanism_text == "unmatched":
            continue
        mechanism = evidence.get("mechanism") or "unmatched"
        if mechanism == "unmatched":
            continue
        pattern_id = f"DP-DEFENSE-{mechanism.upper()}-{r['candidate_id']}"
        if pattern_id in existing_ids:
            continue
        library.setdefault("patterns", []).append(
            {
                "pattern_id": pattern_id,
                "defense_mechanism": mechanism,
                "source": "m5_llm_attribution",
                "confidence": evidence.get("confidence") or "medium",
                "evidence": {
                    "project": _project_of(r.get("candidate_id", "")),
                    "candidate_id": r.get("candidate_id"),
                    "mutation": r.get("candidate_id"),
                    "observation": evidence.get("root_cause")
                    or f"LLM attributed '{mechanism_text}' as the defense mechanism",
                    "evidence_files": [],
                },
                "inference": f"LLM (deepseek-v4-flash) attributed defense mechanism '{mechanism_text}' from runtime evidence; human/behavior verification recommended",
            }
        )
        existing_ids.add(pattern_id)
        added.append(pattern_id)

    library.setdefault("backfilled_at", datetime.now(timezone.utc).isoformat())
    save_library(library, library_path)
    return {"added": added, "total_patterns": len(library.get("patterns", []))}


def _project_of(candidate_id: str) -> str:
    if candidate_id.startswith("OB-"):
        return "online-boutique"
    if candidate_id.startswith("OTEL-"):
        return "otel-demo"
    if candidate_id.startswith("TT-"):
        return "train-ticket"
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        default=EXECUTION_DIR / "llm_interpret_results_dual.json",
    )
    parser.add_argument("--library", type=Path, default=LIBRARY_PATH)
    args = parser.parse_args()
    if not args.results.exists():
        raise SystemExit(f"results not found: {args.results}")
    report = backfill(args.results, args.library)
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
