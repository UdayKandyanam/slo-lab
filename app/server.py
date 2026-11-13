"""Sample service for SLO Lab.

A small HTTP service built on the Python standard library, with
Prometheus metrics from prometheus_client. It exists so the SLO,
alerts, and dashboard in this repo have real metrics to work with.

Endpoints:
  GET /                      JSON hello
  GET /work                  a tiny unit of work with variable latency
  GET /chaos?error_rate=0.5  set the failure probability for /work
  GET /metrics               Prometheus metrics
"""

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests served by the sample service",
    ["method", "path", "status"],
)

DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

_state = {"error_rate": 0.0}
_lock = threading.Lock()


def get_error_rate():
    with _lock:
        return _state["error_rate"]


def set_error_rate(value):
    value = max(0.0, min(1.0, float(value)))
    with _lock:
        _state["error_rate"] = value
    return value


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Keep the console quiet so test output and demo logs stay readable.
        pass

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/metrics":
            body = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        start = time.perf_counter()
        status = 200

        if path == "/":
            payload = {"service": "checkout-api", "status": "ok"}
        elif path == "/work":
            # A tiny bit of work with variable latency, so the histogram
            # has something interesting to show.
            time.sleep(random.uniform(0.005, 0.08))
            if random.random() < get_error_rate():
                status = 500
                payload = {"error": "injected failure"}
            else:
                payload = {"result": "done", "items": random.randint(1, 5)}
        elif path == "/chaos":
            params = parse_qs(parsed.query)
            if "error_rate" in params:
                try:
                    value = set_error_rate(params["error_rate"][0])
                except ValueError:
                    status = 400
                    payload = {"error": "error_rate must be a number between 0 and 1"}
                else:
                    payload = {"error_rate": value}
            else:
                payload = {"error_rate": get_error_rate()}
        else:
            status = 404
            payload = {"error": "not found"}

        DURATION.labels(method="GET", path=path).observe(time.perf_counter() - start)
        REQUESTS.labels(method="GET", path=path, status=str(status)).inc()
        self._send_json(status, payload)


def build_server(host, port):
    return ThreadingHTTPServer((host, port), Handler)


def main():
    import os

    port = int(os.environ.get("PORT", "8080"))
    server = build_server("0.0.0.0", port)
    print(f"checkout-api sample service listening on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
