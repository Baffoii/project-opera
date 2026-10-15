"""Local stand-in for Nominatim so browser E2E runs never touch the public service.
Usage: python tests/opera/e2e/nominatim_stub.py 8099   (then OPERA_CONTEXT_BASE_URL=http://127.0.0.1:8099)
GET /__mode/ok | /__mode/fail switches between answering and returning HTTP 500."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

state = {"mode": "ok", "requests": 0}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/__mode/"):
            state["mode"] = self.path.rsplit("/", 1)[1]
            return self._send(200, state)
        if self.path.startswith("/__state"):
            return self._send(200, state)
        state["requests"] += 1
        if state["mode"] == "fail":
            return self._send(500, {"error": "stub failure"})
        self._send(
            200,
            {"address": {"city": "Stubville", "state": "Test Region", "country": "Testland", "country_code": "tl"}},
        )

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8099), Handler).serve_forever()
