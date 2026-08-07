"""Capture the Online Boutique adservice negative-control state."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def kubectl_json(args: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    completed = subprocess.run(
        ["kubectl", *args, "-o", "json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        return None, (completed.stderr or completed.stdout).strip()
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, f"invalid kubectl JSON: {exc}"
    return value if isinstance(value, dict) else None, None


def summarize_pods(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    result: list[dict[str, Any]] = []
    for pod in data.get("items", []):
        metadata = pod.get("metadata") or {}
        statuses = pod.get("status", {}).get("containerStatuses") or []
        containers = []
        for status in statuses:
            state = status.get("state") or {}
            waiting = state.get("waiting") or {}
            terminated = state.get("terminated") or {}
            containers.append({
                "name": status.get("name"),
                "image": status.get("image"),
                "ready": status.get("ready"),
                "restart_count": status.get("restartCount", 0),
                "waiting_reason": waiting.get("reason"),
                "waiting_message": waiting.get("message"),
                "terminated_reason": terminated.get("reason"),
            })
        ready = any(
            item.get("type") == "Ready" and item.get("status") == "True"
            for item in pod.get("status", {}).get("conditions", [])
            if isinstance(item, dict)
        )
        result.append({
            "name": metadata.get("name"),
            "phase": pod.get("status", {}).get("phase"),
            "ready": ready,
            "containers": containers,
        })
    return result


def summarize_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path).replace("\\", "/")}
    data = json.loads(path.read_text(encoding="utf-8"))
    requests = data.get("requests") or []
    statuses = [item.get("status_code") for item in requests]
    return {
        "available": True,
        "path": str(path).replace("\\", "/"),
        "request_count": len(requests),
        "status_codes": statuses,
        "all_http_200": bool(requests) and all(value == 200 for value in statuses),
        "median_latency_ms": data.get("summary", {}).get("median_latency_ms"),
    }


def capture(namespace: str, baseline: Path) -> dict[str, Any]:
    data, error = kubectl_json(["get", "pods", "-n", namespace, "-l", "app=adservice"])
    pods = summarize_pods(data)
    return {
        "schema_version": 1,
        "tool": "capture_ob_negative_control",
        "captured_at": now(),
        "namespace": namespace,
        "selector": {"app": "adservice"},
        "injection_executed": False,
        "negative_control": "adservice_image_pull_failure",
        "pod_query_error": error,
        "pods": pods,
        "adservice_ready": bool(pods) and any(pod["ready"] for pod in pods),
        "frontend_baseline": summarize_baseline(baseline),
        "classification": "negative_control_non_core_degradation",
        "interpretation": (
            "The adservice image is unavailable in this local cluster; this is an environment "
            "negative control and is not counted as a method-induced application failure."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="online-boutique-lab")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.namespace, args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
