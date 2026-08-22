"""Vercel request adapter for the working HYDRA dashboard. Does not write data/latest.json."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from hydra.dashboard import (
    FAULT_PRESETS,
    DashboardContext,
    _page,
    _reset_circuit,
    _run_heal,
    load_live,
    run_break_demo,
)
from hydra.factory import HydraApp
from hydra.live_snapshot import FAULTS_NAME, LIVE_NAME

_LOCK = threading.RLock()
_APP: HydraApp | None = None
_CTX: DashboardContext | None = None


def _fill_env(key: str, value: str) -> None:
    if not (os.environ.get(key) or "").strip():
        os.environ[key] = value


def configure_vercel_env() -> None:
    if not os.environ.get("VERCEL"):
        return
    tmp = Path("/tmp/hydra-vercel")
    tmp.mkdir(parents=True, exist_ok=True)
    _fill_env("HYDRA_MODE", "replay")
    _fill_env("HYDRA_DASHBOARD_CONTROLS", "1")
    _fill_env("HYDRA_OTEL_DISABLED", "1")
    _fill_env("HYDRA_DASHBOARD_QUIET", "1")
    _fill_env("HYDRA_DETECT_INTERVAL_S", "15")
    _fill_env("HYDRA_HEAL_BUDGET_PER_HOUR", "5")
    _fill_env("HYDRA_FINGERPRINT_ESCALATION", "3")
    _fill_env("HYDRA_MAX_ATTEMPTS_PER_INCIDENT", "4")
    _fill_env("HYDRA_APPROVAL_TIMEOUT_S", "300")
    _fill_env("HYDRA_BACKOFF_BASE_S", "0")
    _fill_env("HYDRA_DB_PATH", str(tmp / "hydra.duckdb"))
    _fill_env("HYDRA_LIVE_PATH", str(tmp / LIVE_NAME))
    _fill_env("HYDRA_FAULTS_PATH", str(tmp / FAULTS_NAME))


def _source() -> str:
    return os.environ.get("HYDRA_DASHBOARD_SOURCE") or "amazon_products"


def get_context() -> DashboardContext:
    global _APP, _CTX
    configure_vercel_env()
    with _LOCK:
        if _CTX is not None and _APP is not None:
            return _CTX
        app = HydraApp()
        token = (os.environ.get("HYDRA_DASHBOARD_TOKEN") or "").strip()
        controls = (os.environ.get("HYDRA_DASHBOARD_CONTROLS") or "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        } or bool(token)
        ctx = DashboardContext(
            live_path=app.live_path,
            faults_path=app.faults_path,
            source=_source(),
            token=token,
            app=app,
            controls=controls,
            watch=False,
        )
        if ctx.controls:
            try:
                app.prepare_demo(ctx.source)
            except Exception:
                try:
                    app.reset_circuit(ctx.source)
                except Exception:
                    pass
        from hydra.live_snapshot import write_snapshot

        try:
            asyncio.run(app.ingest(ctx.source))
        except Exception:
            write_snapshot(app, source_id=ctx.source)
        _APP = app
        _CTX = ctx
        return ctx


def reset_runtime() -> None:
    global _APP, _CTX
    with _LOCK:
        if _APP is not None:
            _APP.close()
        _APP = None
        _CTX = None


def _headers_map(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if hasattr(headers, "items") and not isinstance(headers, dict):
        return {str(k).lower(): str(v) for k, v in headers.items()}
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


def _allow(ctx: DashboardContext, headers: dict[str, str], path: str) -> bool:
    if ctx.controls and not ctx.token:
        return True
    if not ctx.token:
        return False
    auth = headers.get("authorization") or ""
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    query = parse_qs(urlparse(path).query)
    token = (
        (headers.get("x-hydra-token") or "").strip()
        or bearer
        or (query.get("token") or [""])[0]
    )
    return token == ctx.token


def _route_path(path: str, headers: dict[str, str]) -> str:
    for key in ("x-forwarded-uri", "x-vercel-original-path", "x-invoke-path"):
        raw = headers.get(key)
        if raw:
            return urlparse(raw).path or "/"
    parsed = urlparse(path or "/")
    route = parsed.path or "/"
    if route in {"/api", "/api/", "/api/index", "/api/dashboard"}:
        return "/"
    return route


def dispatch(
    method: str,
    path: str,
    *,
    headers: Any = None,
    body: bytes | str | dict[str, Any] | None = None,
    ctx: DashboardContext | None = None,
) -> tuple[int, str, bytes]:
    ctx = ctx or get_context()
    header_map = _headers_map(headers)
    route = _route_path(path, header_map)
    method = method.upper()

    if method == "OPTIONS":
        return 204, "text/plain; charset=utf-8", b""

    if method == "GET" and route in {"/", "/index.html"}:
        return 200, "text/html; charset=utf-8", _page(ctx)

    if method == "GET" and route == "/api/live":
        raw = json.dumps(load_live(ctx), indent=2, default=str).encode()
        return 200, "application/json; charset=utf-8", raw

    if method != "POST" or route not in {"/api/break", "/api/heal", "/api/reset"}:
        return 404, "text/plain; charset=utf-8", b"not found"

    if not _allow(ctx, header_map, path):
        raw = json.dumps(
            {
                "ok": False,
                "error": "dashboard is read-only; set HYDRA_DASHBOARD_CONTROLS=1 or HYDRA_DASHBOARD_TOKEN",
            }
        ).encode()
        return 403, "application/json; charset=utf-8", raw

    parsed: dict[str, Any]
    if isinstance(body, dict):
        parsed = body
    else:
        raw_body = body or b"{}"
        if isinstance(raw_body, str):
            raw_body = raw_body.encode()
        try:
            loaded = json.loads(raw_body.decode() or "{}")
        except json.JSONDecodeError:
            return 400, "application/json; charset=utf-8", b'{"ok": false, "error": "invalid json"}'
        parsed = loaded if isinstance(loaded, dict) else {}

    source = str(parsed.get("source") or ctx.source)
    if route == "/api/break":
        fault = str(parsed.get("fault") or "http_403")
        preset = FAULT_PRESETS.get(fault, {})
        cfg = dict(preset.get("cfg") or {})
        cfg.update({k: v for k, v in parsed.items() if k not in {"source", "fault"}})
        cfg.setdefault("once", True)
        try:
            payload = run_break_demo(ctx, source, fault, cfg)
        except KeyError as exc:
            raw = json.dumps({"ok": False, "error": str(exc)}).encode()
            return 400, "application/json; charset=utf-8", raw
        raw = json.dumps(payload, indent=2, default=str).encode()
        return 200, "application/json; charset=utf-8", raw

    if route == "/api/reset":
        _reset_circuit(ctx, source)
        raw = json.dumps(
            {"ok": True, "reset": source, "live": load_live(ctx)},
            indent=2,
            default=str,
        ).encode()
        return 200, "application/json; charset=utf-8", raw

    try:
        resolutions = _run_heal(ctx, source)
    except RuntimeError as exc:
        raw = json.dumps({"ok": False, "error": str(exc)}).encode()
        return 409, "application/json; charset=utf-8", raw
    raw = json.dumps(
        {"ok": True, "resolutions": resolutions, "live": load_live(ctx)},
        indent=2,
        default=str,
    ).encode()
    return 200, "application/json; charset=utf-8", raw
