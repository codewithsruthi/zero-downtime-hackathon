from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from hydra.config import load_dotenv


def signoz_configured() -> bool:
    load_dotenv()
    return bool(os.environ.get("SIGNOZ_INSTANCE_URL") and os.environ.get("SIGNOZ_API_KEY"))


def instance_url() -> str:
    load_dotenv()
    return (os.environ.get("SIGNOZ_INSTANCE_URL") or "").rstrip("/")


def _request(method: str, path: str, body: Any | None = None, timeout: int = 20) -> tuple[int, Any]:
    load_dotenv()
    key = os.environ.get("SIGNOZ_API_KEY") or ""
    if not key:
        raise RuntimeError("SIGNOZ_API_KEY not set")
    url = instance_url() + path
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "SIGNOZ-API-KEY": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"SigNoz {method} {path} HTTP {exc.code}") from None


def stats() -> dict[str, Any]:
    _, body = _request("GET", "/api/v1/stats")
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body if isinstance(body, dict) else {}


def list_services(start_ms: int, end_ms: int) -> list[Any]:
    payloads = [
        {"start": str(start_ms), "end": str(end_ms)},
        {"start": start_ms, "end": end_ms},
        {"start": str(start_ms * 1_000_000), "end": str(end_ms * 1_000_000)},
    ]
    for body in payloads:
        try:
            _, resp = _request("POST", "/api/v1/services", body)
        except RuntimeError:
            continue
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            for key in ("data", "services"):
                val = resp.get(key)
                if isinstance(val, list):
                    return val
    return []


def traces_for_service(service: str, start_ms: int, end_ms: int, *, limit: int = 10) -> list[dict[str, Any]]:
    body = {
        "start": start_ms,
        "end": end_ms,
        "requestType": "raw",
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "traces",
                        "source": "traces",
                        "filter": {"expression": f"service.name = '{service}'"},
                        "limit": limit,
                    },
                }
            ]
        },
    }
    try:
        _, resp = _request("POST", "/api/v5/query_range", body)
    except RuntimeError:
        return []
    results = (((resp.get("data") or {}).get("data") or {}).get("results") or [])
    if not results:
        return []
    rows = results[0].get("rows") or []
    return [row for row in rows if isinstance(row, dict)]


def fetch_ingestion_key() -> str:
    """Return a Cloud ingestion key (write-only). Not the query API key."""
    _, body = _request("GET", "/api/v2/gateway/ingestion_keys?page=1&per_page=25")
    keys = ((body.get("data") or {}) if isinstance(body, dict) else {}).get("keys") or []
    for item in keys:
        if isinstance(item, dict) and item.get("value"):
            return str(item["value"])
    _, created = _request(
        "POST",
        "/api/v2/gateway/ingestion_keys",
        {"name": "hydra-hackathon", "tags": ["hydra"]},
    )
    data = created.get("data") if isinstance(created, dict) else None
    if not isinstance(data, dict) or not data.get("value"):
        raise RuntimeError("SigNoz did not return an ingestion key")
    return str(data["value"])


def enable_cloud_otel() -> bool:
    """Point HYDRA at SigNoz Cloud OTLP using the workspace ingestion key."""
    load_dotenv()
    os.environ.pop("HYDRA_OTEL_DISABLED", None)
    os.environ.pop("FACTORY_OTEL_DISABLED", None)
    if os.environ.get("HYDRA_MODE", "replay").lower() == "live":
        os.environ["HYDRA_MODE"] = "replay"
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    if not signoz_configured():
        return bool(os.environ.get("SIGNOZ_INGESTION_KEY"))
    ingest = fetch_ingestion_key()
    os.environ["SIGNOZ_INGESTION_KEY"] = ingest
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"signoz-ingestion-key={ingest}"
    return True
