"""Probe fixed-deployment API surfaces with bounded GETs only.

The script never sends a business write, reads Secret values, or persists raw
responses. It records status, bounded metadata and a body hash as H3 evidence.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


CASES = {
    "immich": [("ping", "/api/server/ping"), ("openapi", "/api/openapi.json")],
    "medusa": [("regions", "/store/regions"), ("products", "/store/products?limit=1")],
    "rocketchat": [("info", "/api/v1/info"), ("settings", "/api/v1/settings.public")],
    "erpnext": [("logged-user", "/api/method/frappe.auth.get_logged_user"), ("todos", "/api/resource/ToDo?limit_page_length=1")],
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def probe(url: str) -> dict:
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    opener = build_opener(ProxyHandler({}))
    started = time.monotonic()
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read(1024 * 1024 + 1)
            status = int(response.status)
            headers = dict(response.headers.items())
    except HTTPError as exc:
        with exc:
            body = exc.read(1024 * 1024 + 1)
            status = int(exc.code)
            headers = dict(exc.headers.items())
    except (OSError, URLError, TimeoutError) as exc:
        return {"status": "unreachable", "error_type": type(exc).__name__, "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}
    if len(body) > 1024 * 1024:
        return {"status": "response_too_large", "http_status": status}
    summary = {"status": "observed", "http_status": status, "body_bytes": len(body),
               "body_sha256": hashlib.sha256(body).hexdigest(),
               "content_type": headers.get("Content-Type", "")[:120],
               "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}
    try:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            summary["top_level_keys"] = sorted(str(k) for k in value.keys())[:64]
        elif isinstance(value, list):
            summary["top_level_type"] = "array"
            summary["array_length"] = min(len(value), 100000)
        else:
            summary["top_level_type"] = type(value).__name__
    except (UnicodeDecodeError, json.JSONDecodeError):
        summary["top_level_type"] = "non_json"
    return summary


def collect(root: Path, context: str, output: Path) -> dict:
    reports = []
    for app, paths in CASES.items():
        profile_path = root / "projects" / "chaosatlas-apps" / app / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        namespace = str(profile["namespace_policy"]["allowed_namespaces"][0])
        oracle = profile["business_oracles"][0]
        port = free_port()
        command = ["kubectl", "--context", context, "-n", namespace, "port-forward", f"svc/{oracle['service']}", f"{port}:{int(oracle['remote_port'])}", "--address", "127.0.0.1"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ready = False
        deadline = time.monotonic() + 20
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                        ready = True
                        break
                except OSError:
                    time.sleep(0.1)
            results = []
            if ready:
                for case_id, path in paths:
                    result = probe(f"http://127.0.0.1:{port}{path}")
                    results.append({"id": case_id, "path": path.split("?", 1)[0], **result})
            else:
                results = [{"id": case_id, "path": path.split("?", 1)[0], "status": "port_forward_unavailable"} for case_id, path in paths]
            reports.append({"project_id": app, "namespace": namespace, "service": oracle["service"],
                            "port_forward_ready": ready, "probes": results,
                            "transport_output_tail": "" if ready else "port-forward did not open local socket"})
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    result = {"schema_version": "chaosatlas-four-app-api-readonly-v1", "claim_scope": "read_only_api_surface",
              "context": context, "collected_at": datetime.now(timezone.utc).isoformat(), "projects": reports,
              "writes_performed": False, "secrets_read": False, "raw_responses_persisted": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--context", default="chaosatlas-apps")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = collect(Path(args.root).resolve(), args.context, Path(args.output).resolve())
    print(json.dumps({"status": "collected", "projects": len(result["projects"]), "output": str(Path(args.output).resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
