"""Small HTTP canary with an explicit disposable IO path and clock oracle."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time


DATA_PATH = "/data/chaosatlas-io-probe"
CONTROL_PATH = "/tmp/chaosatlas-extension-control.json"
CONTROL_LOCK = threading.Lock()
CONTROL: dict[str, object] = {}


def refresh_control() -> dict[str, object]:
    """Read the disposable agent control file and fail closed on bad input."""
    global CONTROL
    try:
        with open(CONTROL_PATH, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            value = {}
    except (FileNotFoundError, OSError, ValueError):
        value = {}
    with CONTROL_LOCK:
        CONTROL = value
        return dict(CONTROL)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict[str, object]) -> None:
        body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        control = refresh_control()
        if self.path == "/health":
            self._send(200, {"status": "ok"})
            return
        if self.path == "/clock":
            self._send(200, {"epoch": time.time()})
            return
        if self.path == "/io":
            try:
                payload = ("chaosatlas-io-probe\n" * 1024).encode("utf-8")
                with open(DATA_PATH, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                with open(DATA_PATH, "rb") as handle:
                    observed = len(handle.read())
                os.unlink(DATA_PATH)
                self._send(200, {"status": "ok", "bytes": observed})
            except OSError as exc:
                self._send(503, {"status": "io_error", "error": type(exc).__name__})
            return
        if self.path == "/queue":
            if control.get("mode") == "queue_backlog":
                self._send(200, {"status": "backlog", "queue_name": control.get("queue_name"), "depth": control.get("depth")})
            else:
                self._send(200, {"status": "ok", "queue_name": "chaosatlas-test-queue", "depth": 0})
            return
        if self.path == "/pool":
            if control.get("mode") == "connection_pool_exhaustion":
                connections = control.get("connections")
                self._send(200, {"status": "exhausted", "pool_name": control.get("pool_name"), "in_use": connections, "capacity": connections, "utilization_pct": 100})
            else:
                self._send(200, {"status": "ok", "pool_name": "chaosatlas-test-pool", "in_use": 0, "capacity": 20, "utilization_pct": 0})
            return
        if self.path == "/runtime":
            if control.get("mode") == "runtime_pause":
                self._send(503, {"status": "paused", "target_process": control.get("target_process"), "pause_ms": control.get("pause_ms")})
            else:
                self._send(200, {"status": "ok", "target_process": "python"})
            return
        self._send(404, {"status": "not_found"})

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
