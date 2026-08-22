"""Vercel BaseHTTPRequestHandler entry for the HYDRA dashboard."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from hydra.vercel_runtime import dispatch


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _write(self, code: int, content_type: str, body: bytes) -> None:
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

    def _handle(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b""
        code, content_type, body = dispatch(method, self.path, headers=self.headers, body=raw)
        self._write(code, content_type, body)

    def do_OPTIONS(self) -> None:
        self._write(204, "text/plain; charset=utf-8", b"")

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")
