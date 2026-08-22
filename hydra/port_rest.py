from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from hydra.config import load_dotenv


def port_configured() -> bool:
    load_dotenv()
    return bool(
        os.environ.get("PORT_CLIENT_ID")
        and os.environ.get("PORT_CLIENT_SECRET")
        and os.environ.get("PORT_API_URL")
        and os.environ.get("HYDRA_PORT_DISABLED") != "1"
    )


def _base() -> str:
    load_dotenv()
    return (os.environ.get("PORT_API_URL") or "https://api.getport.io").rstrip("/")


def access_token() -> str:
    load_dotenv()
    client_id = os.environ.get("PORT_CLIENT_ID") or ""
    secret = os.environ.get("PORT_CLIENT_SECRET") or ""
    if not client_id or not secret:
        raise RuntimeError("PORT_CLIENT_ID / PORT_CLIENT_SECRET not set")
    payload = json.dumps({"clientId": client_id, "clientSecret": secret}).encode()
    req = urllib.request.Request(
        f"{_base()}/v1/auth/access_token",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Port auth failed HTTP {exc.code}") from exc
    token = body.get("accessToken") or body.get("access_token")
    if not token:
        raise RuntimeError("Port auth returned no access token")
    return token


def _request(method: str, path: str, *, token: str, body: Any | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{_base()}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Port {method} {path} HTTP {exc.code}: {detail}") from exc


def upsert_blueprint(blueprint: dict[str, Any], *, token: str | None = None) -> None:
    tok = token or access_token()
    identifier = urllib.parse.quote(blueprint["identifier"], safe="")
    try:
        _request("PUT", f"/v1/blueprints/{identifier}", token=tok, body=blueprint)
    except RuntimeError:
        _request("POST", "/v1/blueprints", token=tok, body=blueprint)


def upsert_entity(
    blueprint: str,
    identifier: str,
    properties: dict[str, Any],
    *,
    relations: dict[str, Any] | None = None,
    token: str | None = None,
) -> None:
    tok = token or access_token()
    bp = urllib.parse.quote(blueprint, safe="")
    body: dict[str, Any] = {"identifier": identifier, "properties": properties}
    if relations:
        body["relations"] = relations
    _request(
        "POST",
        f"/v1/blueprints/{bp}/entities?upsert=true&merge=true",
        token=tok,
        body=body,
    )


def delete_entity(blueprint: str, identifier: str, *, token: str | None = None) -> None:
    tok = token or access_token()
    bp = urllib.parse.quote(blueprint, safe="")
    ident = urllib.parse.quote(identifier, safe="")
    try:
        _request("DELETE", f"/v1/blueprints/{bp}/entities/{ident}", token=tok)
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise


def get_entity(blueprint: str, identifier: str, *, token: str | None = None) -> dict[str, Any]:
    tok = token or access_token()
    bp = urllib.parse.quote(blueprint, safe="")
    ident = urllib.parse.quote(identifier, safe="")
    _status, body = _request("GET", f"/v1/blueprints/{bp}/entities/{ident}", token=tok)
    return body if isinstance(body, dict) else {}


def upsert_scorecard(scorecard: dict[str, Any], *, token: str | None = None) -> None:
    tok = token or access_token()
    blueprint = urllib.parse.quote(scorecard["blueprint"], safe="")
    ident = urllib.parse.quote(scorecard["identifier"], safe="")
    body = {k: v for k, v in scorecard.items() if k != "blueprint"}
    try:
        _request(
            "PUT",
            f"/v1/blueprints/{blueprint}/scorecards/{ident}",
            token=tok,
            body=body,
        )
    except RuntimeError:
        _request(
            "POST",
            f"/v1/blueprints/{blueprint}/scorecards",
            token=tok,
            body=body,
        )


def list_blueprints(*, token: str | None = None) -> list[str]:
    tok = token or access_token()
    _status, body = _request("GET", "/v1/blueprints", token=tok)
    rows = body.get("blueprints") if isinstance(body, dict) else body
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if isinstance(row, dict) and row.get("identifier"):
            out.append(row["identifier"])
    return out
