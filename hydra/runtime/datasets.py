"""Bright Data Web Scraper API (Datasets v3).

Amazon Products dataset: gd_l7q7dkf244hwjntr0
Collection from the control-panel URL: hl_bbd9eb9a
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from hydra.errors import AcquisitionError

API_ROOT = "https://api.brightdata.com"
AMAZON_PRODUCTS_DATASET_ID = "gd_l7q7dkf244hwjntr0"
AMAZON_COLLECTION_ID = "hl_bbd9eb9a"

DEFAULT_PRODUCT_URLS = [
    "https://www.amazon.com/dp/B0CHHSFMRL",
    "https://www.amazon.com/dp/B09V3KXJPB",
    "https://www.amazon.com/dp/B0BDJ279KF",
    "https://www.amazon.com/dp/B0BSHF7WHW",
    "https://www.amazon.com/dp/B0D1XD1ZV3",
    "https://www.amazon.com/dp/B09G9FPHY6",
    "https://www.amazon.com/dp/B0BSHF7T3T",
    "https://www.amazon.com/dp/B0C1H26C46",
    "https://www.amazon.com/dp/B0CQT1Y6XC",
    "https://www.amazon.com/dp/B0C26B8PQ7",
]


def api_token() -> str | None:
    token = (
        os.environ.get("BRIGHTDATA_API_TOKEN")
        or os.environ.get("BRIGHTDATA_API_KEY")
        or ""
    ).strip()
    return token or None


def scrape_dataset(args: dict[str, Any], *, timeout_s: float = 180) -> str:
    """Collect structured rows. Prefers an existing snapshot, then a sync scrape."""
    from hydra.config import load_dotenv

    load_dotenv()
    token = api_token()
    if not token:
        raise AcquisitionError(
            "BRIGHTDATA_API_TOKEN (or BRIGHTDATA_API_KEY) is empty",
            error_type="ConfigError",
            http_status=401,
        )
    dataset_id = (
        args.get("dataset_id")
        or os.environ.get("BRIGHTDATA_DATASET_ID")
        or AMAZON_PRODUCTS_DATASET_ID
    )
    collection_id = (
        args.get("collection_id")
        or os.environ.get("BRIGHTDATA_COLLECTION_ID")
        or AMAZON_COLLECTION_ID
    )
    urls = list(args.get("urls") or DEFAULT_PRODUCT_URLS)
    snapshot_id = args.get("snapshot_id")

    if snapshot_id:
        return _download_snapshot(token, snapshot_id)
    downloaded = _try_download(token, collection_id)
    if downloaded:
        return downloaded
    ready = _latest_ready_snapshot(token, dataset_id)
    if ready:
        return _download_snapshot(token, ready)
    return _scrape_or_trigger(token, dataset_id, urls, timeout_s=timeout_s)


def _scrape_or_trigger(token: str, dataset_id: str, urls: list[str], *, timeout_s: float) -> str:
    body = [{"url": url} for url in urls]
    try:
        payload, status = _request(
            "POST",
            "/datasets/v3/scrape",
            token=token,
            params={"dataset_id": dataset_id, "format": "json"},
            json_body=body,
            timeout_s=timeout_s,
        )
        if status == 200 and payload.strip():
            _ensure_json_rows(payload)
            return payload
    except AcquisitionError as exc:
        if exc.http_status not in {408, 429, 500, 502, 503, 504}:
            raise
    snapshot = _request_json(
        "POST",
        "/datasets/v3/trigger",
        token=token,
        params={"dataset_id": dataset_id, "format": "json"},
        json_body=body,
        timeout_s=30,
    )
    snapshot_id = snapshot.get("snapshot_id") if isinstance(snapshot, dict) else None
    if not snapshot_id:
        raise AcquisitionError(
            f"trigger did not return snapshot_id: {snapshot!r}",
            error_type="HTTPError",
            http_status=502,
        )
    _wait_ready(token, snapshot_id, timeout_s=timeout_s)
    return _download_snapshot(token, snapshot_id)


def _try_download(token: str, snapshot_id: str) -> str | None:
    try:
        payload = _download_snapshot(token, snapshot_id)
    except AcquisitionError as exc:
        if exc.http_status in {404, 400}:
            return None
        raise
    if not payload.strip():
        return None
    try:
        _ensure_json_rows(payload)
    except AcquisitionError:
        return None
    return payload


def _latest_ready_snapshot(token: str, dataset_id: str) -> str | None:
    try:
        listing = _request_json(
            "GET",
            "/datasets/v3/snapshots",
            token=token,
            params={"dataset_id": dataset_id, "status": "ready", "limit": "5"},
            timeout_s=30,
        )
    except AcquisitionError:
        return None
    rows = listing if isinstance(listing, list) else listing.get("snapshots") or []
    if not rows:
        return None
    first = rows[0]
    return first.get("id") if isinstance(first, dict) else None


def _wait_ready(token: str, snapshot_id: str, *, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        progress = _request_json(
            "GET",
            f"/datasets/v3/progress/{urllib.parse.quote(snapshot_id)}",
            token=token,
            timeout_s=30,
        )
        status = (progress or {}).get("status") if isinstance(progress, dict) else None
        if status == "ready":
            return
        if status in {"failed", "canceled"}:
            raise AcquisitionError(
                f"snapshot {snapshot_id} {status}",
                error_type="HTTPError",
                http_status=502,
            )
        time.sleep(3)
    raise AcquisitionError(
        f"snapshot {snapshot_id} not ready within {timeout_s}s",
        error_type="Timeout",
        http_status=408,
    )


def _download_snapshot(token: str, snapshot_id: str) -> str:
    payload, status = _request(
        "GET",
        f"/datasets/v3/snapshot/{urllib.parse.quote(snapshot_id)}",
        token=token,
        params={"format": "json"},
        timeout_s=60,
    )
    if status != 200 or not payload.strip():
        raise AcquisitionError(
            f"empty snapshot {snapshot_id}",
            error_type="EmptyBody",
            http_status=status,
        )
    return payload


def _ensure_json_rows(payload: str) -> list[dict[str, Any]]:
    data = json.loads(payload)
    if isinstance(data, dict):
        data = data.get("data") or data.get("results") or [data]
    if not isinstance(data, list) or not data:
        raise AcquisitionError("dataset returned no rows", error_type="EmptyBody")
    return [row for row in data if isinstance(row, dict)]


def _request_json(method: str, path: str, **kwargs) -> Any:
    payload, _status = _request(method, path, **kwargs)
    if not payload.strip():
        return {}
    return json.loads(payload)


def _request(
    method: str,
    path: str,
    *,
    token: str,
    params: dict[str, str] | None = None,
    json_body: Any | None = None,
    timeout_s: float = 60,
) -> tuple[str, int]:
    url = API_ROOT + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = None if json_body is None else json.dumps(json_body).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.read().decode("utf-8"), resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise AcquisitionError(
            f"Bright Data {method} {path} failed: {exc.code} {detail}",
            error_type="HTTPError",
            http_status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise AcquisitionError(
            f"Bright Data {method} {path} unreachable: {exc.reason}",
            error_type="Timeout",
            http_status=503,
        ) from exc
