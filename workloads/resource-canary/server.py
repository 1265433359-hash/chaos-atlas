from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import socket


BODY = b"chaosatlas-resource-canary"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/dns-check":
            hostname = os.environ.get("CHAOSATLAS_DNS_HOSTNAME", "kubernetes.default.svc.cluster.local")
            try:
                socket.gethostbyname(hostname)
            except OSError:
                body = b"chaosatlas-dns-unavailable"
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *_args):
        pass


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
