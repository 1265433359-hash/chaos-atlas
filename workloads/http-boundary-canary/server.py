from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


CONTROL = Path("/tmp/chaosatlas-http-control.json")
BODY = b"chaosatlas-http-boundary-canary"
_lock = threading.Lock()
_request_times: list[float] = []


def control() -> dict:
    try:
        value = json.loads(CONTROL.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


class DependencyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if control().get("mode") == "dependency_unreachable":
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args):
        pass


class MainHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        current = control()
        if current.get("mode") == "rate_limit":
            now = time.monotonic()
            window = int(current.get("window_s") or 10)
            limit = int(current.get("requests_per_window") or 2)
            with _lock:
                _request_times[:] = [stamp for stamp in _request_times if now - stamp < window]
                if len(_request_times) >= limit:
                    self.send_response(int(current.get("status_code") or 429))
                    self.end_headers()
                    return
                _request_times.append(now)
        try:
            with urlopen("http://127.0.0.1:8081/health", timeout=1) as response:
                if response.status != 200:
                    raise URLError(f"dependency returned {response.status}")
        except (OSError, URLError):
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *_args):
        pass


def serve(server: HTTPServer) -> None:
    server.serve_forever(poll_interval=0.1)


dependency = HTTPServer(("0.0.0.0", 8081), DependencyHandler)
main = HTTPServer(("0.0.0.0", 8080), MainHandler)
threading.Thread(target=serve, args=(dependency,), daemon=True).start()
serve(main)
