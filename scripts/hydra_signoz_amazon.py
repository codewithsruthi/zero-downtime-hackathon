#!/usr/bin/env python3
"""Replay HYDRA ingest with OTEL on so traces land in SigNoz."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hydra.config import load_dotenv
from hydra.factory import HydraApp
from hydra.signoz_rest import (
    fetch_ingestion_key,
    instance_url,
    signoz_configured,
    stats,
    traces_for_service,
)
from hydra.telemetry import shutdown_telemetry, telemetry_enabled, telemetry_status

AMAZON = "amazon_products"
SERVICE = "hydra-ingestion"


async def _ingest(app: HydraApp) -> list:
    results = []
    amazon = app.contracts.get(AMAZON)
    snap = app.store.latest_good_raw(AMAZON) or app.store.latest_raw(AMAZON)
    if snap:
        results.append(
            await app.runtime.execute(amazon, skip_acquire=True, snapshot=snap, reason="signoz")
        )
    else:
        results.append(await app.ingest(AMAZON))
    for source_id in app.contracts.ids():
        if source_id == AMAZON:
            continue
        results.append(await app.ingest(source_id))
    return results


def _upsert_env(updates: dict[str, str]) -> None:
    path = ROOT / ".env"
    lines = path.read_text().splitlines() if path.is_file() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n")


def main() -> int:
    load_dotenv()
    os.environ.pop("HYDRA_OTEL_DISABLED", None)
    os.environ.pop("FACTORY_OTEL_DISABLED", None)
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        print("OTEL_EXPORTER_OTLP_ENDPOINT is not set")
        return 1
    if os.environ.get("HYDRA_MODE", "replay").lower() == "live":
        os.environ["HYDRA_MODE"] = "replay"
    if signoz_configured():
        ingest = fetch_ingestion_key()
        os.environ["SIGNOZ_INGESTION_KEY"] = ingest
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"signoz-ingestion-key={ingest}"
        _upsert_env(
            {
                "SIGNOZ_INGESTION_KEY": ingest,
                "OTEL_EXPORTER_OTLP_HEADERS": f"signoz-ingestion-key={ingest}",
            }
        )
        print("using SigNoz Cloud ingestion key from Settings/gateway (query API key is not used for OTLP)")

    app = HydraApp()
    try:
        if not telemetry_enabled():
            status = telemetry_status()
            print(
                "telemetry is off; install opentelemetry packages "
                f"and confirm OTLP endpoint ({status.get('last_error') or 'no tracer'})"
            )
            return 1
        results = asyncio.run(_ingest(app))
        for result in results:
            print(
                f"{result.source_id}: {result.status} rows={result.rows_out} "
                f"run={result.run_id} trace={result.trace_id or '-'}"
            )
    finally:
        shutdown_telemetry()
        app.close()

    status = telemetry_status()
    print(
        f"otel export={status.get('last_export') or 'unknown'} "
        f"spans={status.get('exported')} err={status.get('last_error') or '-'}"
    )
    if status.get("last_export") == "fail":
        print(
            "OTLP export failed. SigNoz Cloud needs an ingestion key from "
            "Settings → Ingestion (this is not the same as the query API key)."
        )
        return 1

    ui = instance_url()
    print(f"SigNoz UI: {ui}")
    print(f"filter service.name = {SERVICE} and hydra.source_id = {AMAZON}")

    if not signoz_configured():
        print("SIGNOZ_API_KEY / SIGNOZ_INSTANCE_URL missing; skip query verify")
        return 0

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 15 * 60 * 1000
    seen = False
    amazon_hit = False
    for attempt in range(6):
        time.sleep(5 if attempt else 8)
        try:
            snapshot = stats()
            rows = traces_for_service(SERVICE, start_ms, int(time.time() * 1000), limit=20)
        except RuntimeError as exc:
            print(f"SigNoz query: {exc}")
            continue
        traces_last = snapshot.get("telemetry.traces.last_observed.time")
        traces_count = snapshot.get("telemetry.traces.count")
        sources = []
        for row in rows:
            data = row.get("data") if isinstance(row.get("data"), dict) else row
            attrs = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
            source = attrs.get("hydra.source_id")
            if source:
                sources.append(str(source))
        print(
            f"poll {attempt + 1}: spans={len(rows)} sources={sorted(set(sources)) or '-'} "
            f"traces_last={traces_last} count={traces_count}"
        )
        if rows:
            seen = True
        if AMAZON in sources:
            amazon_hit = True
            break
    if amazon_hit:
        print(f"confirmed {SERVICE} traces in SigNoz for {AMAZON}")
        return 0
    if seen:
        print(f"confirmed {SERVICE} traces in SigNoz")
        return 0
    print(
        f"export succeeded; if {SERVICE} is not listed yet, wait ~30s then open Traces in SigNoz"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
