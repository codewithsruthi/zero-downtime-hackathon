from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hydra.vercel_runtime import dispatch


def _route(path: str) -> str:
    query = parse_qs(urlparse(path).query)
    if query.get("route"):
        return query["route"][0]
    parsed = urlparse(path).path or "/"
    if parsed in {"/api", "/api/", "/api/index"}:
        return "/"
    return parsed


try:
    from flask import Flask, Response, request

    app = Flask(__name__)

    @app.route("/", methods=["GET", "POST", "OPTIONS"])
    @app.route("/<path:unused>", methods=["GET", "POST", "OPTIONS"])
    def entry(unused: str = "") -> Response:
        route = request.args.get("route") or _route(request.full_path)
        code, content_type, body = dispatch(
            request.method,
            route,
            headers=request.headers,
            body=request.get_data(),
        )
        resp = Response(body, status=code, content_type=content_type)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp
except ImportError:
    app = None


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _go(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            code, content_type, body = dispatch(
                method,
                _route(self.path),
                headers=self.headers,
                body=raw,
            )
        except Exception as exc:
            msg = f"hydra error: {type(exc).__name__}: {exc}".encode()
            code, content_type, body = 500, "text/plain; charset=utf-8", msg
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Hydra-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._go("OPTIONS")

    def do_GET(self) -> None:
        self._go("GET")

    def do_POST(self) -> None:
        self._go("POST")
