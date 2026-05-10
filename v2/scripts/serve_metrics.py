"""Serve Hermes telemetry metrics for local/ops dashboards.

Exposes:
- GET /metrics   Prometheus-style metrics from telemetry counters/latency.
- GET /healthz   Basic liveness probe.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, "v2")
from agent.telemetry import telemetry


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/metrics":
            payload = telemetry.export_prometheus().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Keep this endpoint quiet by default.
        return


def main() -> int:
    server = HTTPServer(("0.0.0.0", 9464), Handler)
    print("Hermes metrics server listening on http://0.0.0.0:9464/metrics")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
