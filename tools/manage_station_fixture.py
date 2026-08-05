"""Create or delete a temporary Station-service fixture through the service API."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_chaos_experiment import http_request, start_port_forward, stop_process, wait_for_port


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "delete"])
    parser.add_argument("--namespace", default="train-ticket-lab")
    parser.add_argument("--service", default="ts-station-service")
    parser.add_argument("--remote-port", type=int, default=12345)
    parser.add_argument("--local-port", type=int, default=18084)
    parser.add_argument("--name", required=True)
    parser.add_argument("--station-id")
    parser.add_argument("--stay-time", type=int, default=7)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if args.action == "delete" and not args.station_id:
        raise SystemExit("--station-id is required for delete")

    process = start_port_forward(args.namespace, args.service, args.local_port, args.remote_port)
    report: dict[str, Any] = {
        "schema_version": 1,
        "tool": "manage_station_fixture",
        "action": args.action,
        "started_at": now(),
        "namespace": args.namespace,
        "service": args.service,
        "name": args.name,
        "station_id": args.station_id,
        "stay_time": args.stay_time,
        "request": None,
        "port_forward": None,
        "errors": [],
    }
    try:
        wait_for_port("127.0.0.1", args.local_port, process, timeout=15)
        if args.action == "create":
            request = http_request(
                args.local_port,
                "/api/v1/stationservice/stations",
                "POST",
                10,
                json.dumps({"name": args.name, "stayTime": args.stay_time}),
                16384,
            )
            report["request"] = request
            if request.get("status_code") != 201 and request.get("status_code") != 200:
                report["errors"].append("fixture creation did not return HTTP 200/201")
            else:
                try:
                    body = json.loads(request.get("body") or "{}")
                    data = body.get("data") or {}
                    report["station_id"] = data.get("id")
                    if body.get("status") != 1 or not report["station_id"]:
                        report["errors"].append("fixture creation response did not contain status=1 and data.id")
                except (TypeError, json.JSONDecodeError) as exc:
                    report["errors"].append(f"invalid fixture creation response: {exc}")
        else:
            report["request"] = http_request(
                args.local_port,
                f"/api/v1/stationservice/stations/{args.station_id}",
                "DELETE",
                10,
                None,
                16384,
            )
            if report["request"].get("status_code") not in (200, 204):
                report["errors"].append("fixture deletion did not return HTTP 200/204")
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
