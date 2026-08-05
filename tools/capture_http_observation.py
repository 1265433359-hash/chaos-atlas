"""Capture read-only HTTP observations through an isolated Kubernetes Service."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_chaos_experiment import http_request, start_port_forward, stop_process, wait_for_port


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="train-ticket-lab")
    parser.add_argument("--service", required=True)
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--local-port", type=int, default=18085)
    parser.add_argument("--path", required=True)
    parser.add_argument("--method", default="GET")
    parser.add_argument("--body")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    process = start_port_forward(args.namespace, args.service, args.local_port, args.remote_port)
    report: dict[str, Any] = {
        "schema_version": 1,
        "tool": "capture_http_observation",
        "started_at": now(),
        "namespace": args.namespace,
        "service": args.service,
        "request_config": {
            "remote_port": args.remote_port,
            "local_port": args.local_port,
            "path": args.path,
            "method": args.method.upper(),
            "count": args.count,
            "timeout_sec": args.timeout,
        },
        "requests": [],
        "errors": [],
        "port_forward": None,
    }
    try:
        wait_for_port("127.0.0.1", args.local_port, process, timeout=15)
        for index in range(max(0, args.count)):
            request = http_request(
                args.local_port,
                args.path,
                args.method,
                args.timeout,
                args.body,
                65536,
            )
            request["sample"] = index + 1
            request["observed_at"] = now()
            report["requests"].append(request)
            if index + 1 < args.count:
                time.sleep(max(0.0, args.interval))
    except Exception as exc:  # pragma: no cover - runtime command failures are recorded
        report["errors"].append(str(exc))
    finally:
        report["port_forward"] = stop_process(process)
        report["finished_at"] = now()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
