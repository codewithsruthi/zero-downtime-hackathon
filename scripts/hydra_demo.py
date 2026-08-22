#!/usr/bin/env python3
"""Amazon-only HYDRA demo: show products, break F1 then F2, heal, sync Port."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hydra.config import load_dotenv
from hydra.factory import HydraApp
from hydra.port_catalog import (
    AMAZON,
    hide_seed_sources,
    list_amazon_products,
    sync_amazon_products,
    sync_catalog,
)
from hydra.port_rest import port_configured
from hydra.signoz_rest import enable_cloud_otel, instance_url, signoz_configured, traces_for_service
from hydra.telemetry import shutdown_telemetry, telemetry_enabled, telemetry_status

SERVICE = "hydra-ingestion"


def _print_run(result) -> None:
    print(
        f"  {result.source_id}: {result.status} rows={result.rows_out} "
        f"err={result.error_type} http={result.http_status} "
        f"run={result.run_id} trace={result.trace_id or '-'}"
    )


def _print_port(summaries) -> None:
    if not summaries or summaries[0].get("skipped"):
        print("  Port catalog skipped (no REST keys)")
        return
    for row in summaries:
        if row.get("error"):
            print(f"  port {row['source_id']} error={row['error']}")
            continue
        print(
            f"  port {row['source_id']} health={row.get('health')} "
            f"last_run={row.get('last_run')} rows={row.get('rows')} "
            f"trace={row.get('trace_id') or '-'}"
        )


def _print_products(app: HydraApp, heading: str) -> list[dict]:
    products = list_amazon_products(app)
    print(f"== {heading} ({len(products)} products) ==")
    if not products:
        print("  (no rows in derived_amazon_products)")
        return []
    print(f"  {'ASIN':<14} {'PRICE':>8}  {'AVAIL':<18} TITLE")
    for row in products:
        price = row.get("price")
        price_s = "-" if price is None else f"{float(price):.2f}"
        avail = str(row.get("availability") or "-")[:18]
        title = str(row.get("title") or "")[:56]
        print(f"  {str(row.get('asin') or '-'):<14} {price_s:>8}  {avail:<18} {title}")
    return products


def _products_payload(products: list[dict]) -> list[dict]:
    out = []
    for row in products:
        out.append(
            {
                "asin": row.get("asin"),
                "title": row.get("title"),
                "price": row.get("price"),
                "availability": row.get("availability"),
                "url": row.get("url"),
            }
        )
    return out


async def _happy(app: HydraApp):
    amazon = app.contracts.get(AMAZON)
    snap = app.store.latest_good_raw(AMAZON) or app.store.latest_raw(AMAZON)
    if snap:
        return await app.runtime.execute(amazon, skip_acquire=True, snapshot=snap, reason="demo")
    return await app.ingest(AMAZON)


def _latest_incident(app: HydraApp) -> dict | None:
    rows = app.store.query(
        "SELECT * FROM incident WHERE source_id = ? ORDER BY detected_at DESC LIMIT 1",
        [AMAZON],
    )
    return rows[0] if rows else None


def _heals(app: HydraApp, incident_id: str) -> list[dict]:
    return app.store.query(
        """
        SELECT primitive, attempt, verification_passed, notes
        FROM heal_ledger WHERE incident_id = ? ORDER BY attempt
        """,
        [incident_id],
    )


def _print_incident(app: HydraApp, resolutions: list, wall_s: float) -> tuple[dict | None, list]:
    print(f"  resolutions={resolutions} wall_s={wall_s}")
    incident = _latest_incident(app)
    heals = _heals(app, incident["incident_id"]) if incident else []
    if incident:
        print(
            f"  incident={incident['incident_id']} class={incident['failure_class']} "
            f"resolution={incident['resolution']} mttr_s={incident.get('mttr_seconds')}"
        )
        for heal in heals:
            print(
                f"  {heal['primitive']} attempt={heal['attempt']} "
                f"verified={heal['verification_passed']} {heal.get('notes')}"
            )
    return incident, heals


def _confirm_signoz(trace_id: str | None) -> None:
    if not signoz_configured() or not trace_id:
        return
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 30 * 60 * 1000
    time.sleep(8)
    rows = traces_for_service(SERVICE, start_ms, end_ms, limit=30)
    hit = False
    error = False
    for row in rows:
        data = row.get("data") if isinstance(row.get("data"), dict) else row
        attrs = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
        if attrs.get("hydra.source_id") != AMAZON:
            continue
        if (data.get("trace_id") or "") == trace_id:
            hit = True
            if data.get("status_code_string") == "Error" or data.get("has_error"):
                error = True
    ui = instance_url()
    print(f"  SigNoz {ui} service={SERVICE} source={AMAZON} trace={trace_id}")
    if hit:
        print(f"  SigNoz confirmed trace ({'ERROR' if error else 'OK'})")
    else:
        print("  SigNoz ingest lag: open Traces and filter by the trace id above")


def _beat_heal(name: str, resolutions, incident, heals, mttr) -> dict:
    return {
        "name": name,
        "resolutions": resolutions,
        "incident": incident["incident_id"] if incident else None,
        "failure_class": incident["failure_class"] if incident else None,
        "mttr_s": float(incident["mttr_seconds"])
        if incident and incident.get("mttr_seconds") is not None
        else mttr,
        "heals": [
            {"primitive": h["primitive"], "verified": bool(h["verification_passed"])}
            for h in heals
        ],
    }


async def _run(app: HydraApp) -> dict:
    story: dict = {"beats": [], "source": AMAZON}
    hide_seed_sources()

    print("== 1. Amazon products (happy path) ==")
    happy = await _happy(app)
    _print_run(happy)
    products = _print_products(app, "Amazon catalog")
    story["products"] = _products_payload(products)
    sync_amazon_products(app)
    _print_port(sync_catalog(app, AMAZON))
    story["beats"].append(
        {
            "name": "happy_path",
            "status": happy.status,
            "rows": happy.rows_out,
            "trace": happy.trace_id,
            "run": happy.run_id,
        }
    )

    print("== 2. Loud break: Amazon http_403 ==")
    app.break_source(AMAZON, "http_403")
    broken = await app.ingest(AMAZON)
    _print_run(broken)
    _print_port(sync_catalog(app, AMAZON))
    _confirm_signoz(broken.trace_id)
    story["beats"].append(
        {
            "name": "amazon_403",
            "status": broken.status,
            "http": broken.http_status,
            "trace": broken.trace_id,
            "run": broken.run_id,
        }
    )

    print("== 3. Heal Amazon F1 ==")
    t0 = time.time()
    resolutions = await app.loop.sweep_and_heal(AMAZON)
    incident, heals = _print_incident(app, resolutions, round(time.time() - t0, 3))
    _print_products(app, "Amazon catalog after F1 heal")
    sync_amazon_products(app)
    _print_port(sync_catalog(app, AMAZON))
    story["beats"].append(_beat_heal("amazon_heal_f1", resolutions, incident, heals, time.time() - t0))

    print("== 4. Quiet break: Amazon volume collapse (HTTP 200, too few products) ==")
    app.injector.clear(AMAZON)
    app.break_source(AMAZON, "volume_collapse", keep=2, once=True)
    quiet = await app.ingest(AMAZON)
    _print_run(quiet)
    print(f"  failed_assertions={quiet.failed_assertions}")
    _print_products(app, "Amazon catalog while broken")
    _print_port(sync_catalog(app, AMAZON))
    _confirm_signoz(quiet.trace_id)
    story["beats"].append(
        {
            "name": "amazon_collapse",
            "status": quiet.status,
            "rows_in": quiet.rows_in,
            "rows_out": quiet.rows_out,
            "failed_assertions": quiet.failed_assertions,
            "trace": quiet.trace_id,
            "run": quiet.run_id,
        }
    )

    print("== 5. Heal Amazon F2 ==")
    t1 = time.time()
    resolutions2 = await app.loop.sweep_and_heal(AMAZON)
    incident2, heals2 = _print_incident(app, resolutions2, round(time.time() - t1, 3))
    products = _print_products(app, "Amazon catalog after F2 heal")
    story["products"] = _products_payload(products)
    sync_amazon_products(app)
    _print_port(sync_catalog(app, AMAZON))
    story["beats"].append(_beat_heal("amazon_heal_f2", resolutions2, incident2, heals2, time.time() - t1))

    print("== Amazon incidents ==")
    rows = app.store.query(
        """
        SELECT incident_id, failure_class, resolution, mttr_seconds
        FROM incident WHERE source_id = ? ORDER BY detected_at
        """,
        [AMAZON],
    )
    print(json.dumps(rows, indent=2, default=str))
    story["signoz"] = instance_url() if signoz_configured() else None
    story["port"] = port_configured()
    story["otel"] = telemetry_status()
    return story


def main() -> int:
    load_dotenv()
    os.environ["HYDRA_MODE"] = "replay"
    os.environ["HYDRA_BACKOFF_BASE_S"] = os.environ.get("HYDRA_BACKOFF_BASE_S") or "0"
    enable_cloud_otel()
    app = HydraApp()
    try:
        if not telemetry_enabled():
            print(f"warning: OTEL off ({telemetry_status().get('last_error') or 'no tracer'})")
        story = asyncio.run(_run(app))
    finally:
        shutdown_telemetry()
        app.close()
    (ROOT / "data" / "demo-last.json").write_text(json.dumps(story, indent=2, default=str) + "\n")
    print("wrote data/demo-last.json")
    ui = instance_url() if signoz_configured() else ""
    if ui:
        print(f"SigNoz: {ui}  filter hydra.source_id={AMAZON}")
    if port_configured():
        print("Port: hydra_source/amazon_products and hydra_product (ASINs)")
    f1 = next((b for b in story["beats"] if b["name"] == "amazon_heal_f1"), {})
    f2 = next((b for b in story["beats"] if b["name"] == "amazon_heal_f2"), {})
    if f1.get("resolutions") != ["healed"] or f2.get("resolutions") != ["healed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
