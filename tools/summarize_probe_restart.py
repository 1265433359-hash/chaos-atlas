"""Normalize probe-restart evidence when the runner's business wait times out."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize(report: dict[str, Any], path: Path) -> dict[str, Any]:
    restart = {
        "detected": bool(report.get("restart_detected")),
        "ready_after_restart": bool(report.get("target_ready_after_restart")),
        "timeline": report.get("restart_timeline") or [],
        "target_after_restart": report.get("target_after_restart"),
    }
    after_restart = report.get("after_restart") or {}
    raw_cleanup = report.get("cleanup") or []
    cleanup_items = raw_cleanup if isinstance(raw_cleanup, list) else [raw_cleanup]
    restart_detected = bool(restart.get("detected"))
    ready_after_restart = bool(restart.get("ready_after_restart"))
    connection_failure = any(
        item.get("grpc_status") in {"UNAVAILABLE", "DEADLINE_EXCEEDED"}
        or "refused" in str(item.get("error", "")).lower()
        for item in (after_restart.get("observations") or [])
        if isinstance(item, dict)
    )
    if restart_detected and not ready_after_restart and connection_failure:
        classification = "probe_restart_recovery_timeout"
    elif restart_detected and connection_failure:
        classification = "probe_restart_connection_failure_confirmed"
    else:
        classification = str(report.get("classification") or report.get("result_classification") or "unknown")
    return {
        "schema_version": 1,
        "tool": "summarize_probe_restart",
        "summarized_at": now(),
        "source_report": str(path).replace("\\", "/"),
        "classification": classification,
        "evidence_state": "runtime_effect_observed" if restart_detected else "inconclusive",
        "restart_detected": restart_detected,
        "ready_after_restart": ready_after_restart,
        "connection_failure_after_restart": connection_failure,
        "cleanup_confirmed": bool(cleanup_items) and all(
            item.get("resource_absent_after_delete") and item.get("delete_command_ok")
            for item in cleanup_items
            if isinstance(item, dict)
        ),
        "observed_restart": restart,
        "after_restart_observation": after_restart,
        "interpretation": (
            "A probe-triggered restart was observed while the fault was active; the target did not "
            "become Ready within the configured recovery window and the business client saw a "
            "connection failure. This is counted as recovery amplification, not as a clean escape."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    result = summarize(report, args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
