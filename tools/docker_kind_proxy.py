"""Temporary Docker API proxy for kind on WSL cgroup-v2 hosts.

Only container-create requests are changed: kind's hard-coded private cgroup
namespace is replaced with host so nested systemd in the node can start.
"""
from __future__ import annotations

import http.client
import http.server
import json
import socket
import socketserver
import sys
import select


SOCKET_PATH = "/var/run/docker.sock"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 2376


class UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(SOCKET_PATH)


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write((fmt % args) + "\n")

    def do_request(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        if self.path.split("?", 1)[0].endswith("/containers/create") and body:
            try:
                payload = json.loads(body)
                payload.setdefault("HostConfig", {})["CgroupnsMode"] = "host"
                body = json.dumps(payload, separators=(",", ":")).encode()
            except (ValueError, TypeError):
                pass

        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in {"host", "content-length", "connection"}
        }
        headers["Host"] = "docker"
        headers["Content-Length"] = str(len(body))
        conn = UnixHTTPConnection(SOCKET_PATH)
        conn.request(self.command, self.path, body=body, headers=headers)
        response = conn.getresponse()
        self.send_response(response.status, response.reason)
        upgraded = response.status == 101 or response.getheader("Upgrade") is not None
        for key, value in response.getheaders():
            if key.lower() not in ({"transfer-encoding", "connection", "content-length"} if not upgraded else set()):
                self.send_header(key, value)
        if upgraded:
            self.end_headers()
            upstream = conn.sock
            client = self.connection
            while True:
                ready, _, _ = select.select([client, upstream], [], [], 60)
                if not ready:
                    break
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is client else client).sendall(data)
            return
        data = response.read()
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        conn.close()

    do_GET = do_request
    do_HEAD = do_request
    do_POST = do_request
    do_PUT = do_request
    do_DELETE = do_request


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    server = ThreadingServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    print(f"docker kind proxy listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
