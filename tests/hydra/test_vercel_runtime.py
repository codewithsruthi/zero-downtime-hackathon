from __future__ import annotations

import asyncio
import json

from hydra.dashboard import DashboardContext
from hydra.live_snapshot import write_snapshot
from hydra.vercel_runtime import dispatch


def _ctx(app) -> DashboardContext:
    write_snapshot(app)
    return DashboardContext(
        live_path=app.live_path,
        faults_path=app.faults_path,
        source="amazon_products",
        token="",
        app=app,
        controls=True,
        watch=False,
    )


def test_dispatch_serves_working_dashboard(app):
    ctx = _ctx(app)
    code, content_type, body = dispatch("GET", "/", ctx=ctx)
    assert code == 200
    assert "text/html" in content_type
    html = body.decode()
    assert "HYDRA" in html
    assert "Break Amazon" in html
    assert "Sruthi Anuvalasetty" in html


def test_dispatch_live_catalog(app):
    asyncio.run(app.ingest("amazon_products"))
    ctx = _ctx(app)
    code, content_type, body = dispatch("GET", "/api/live", ctx=ctx)
    assert code == 200
    assert "json" in content_type
    payload = json.loads(body)
    assert payload["source_id"] == "amazon_products"
    assert len(payload["products"]) >= 8


def test_dispatch_break_and_reset(app):
    asyncio.run(app.ingest("amazon_products"))
    ctx = _ctx(app)
    code, _, body = dispatch(
        "POST",
        "/api/break",
        body={"fault": "null_flood", "source": "amazon_products"},
        ctx=ctx,
    )
    assert code == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["injected"] == "null_flood"
    assert payload["live"]["steps"] == {
        "detect": "failed",
        "classify": "failed",
        "guard": "failed",
        "act": "failed",
        "verify": "failed",
    }
    frames = payload["frames"]
    assert len(frames) == 7
    assert frames[1]["steps"]["detect"] == "current"
    assert frames[1]["steps"]["classify"] == "failed"
    assert frames[5]["steps"]["verify"] == "current"
    assert frames[5]["steps"]["detect"] == "done"
    assert frames[-1]["steps"]["verify"] == "done"
    cards = frames[0]["break_view"]["cards"]
    assert cards
    assert any((card.get("_ui") or {}).get("missing_price") for card in cards)

    code, _, body = dispatch("POST", "/api/reset", body={"source": "amazon_products"}, ctx=ctx)
    assert code == 200
    assert json.loads(body)["ok"] is True
