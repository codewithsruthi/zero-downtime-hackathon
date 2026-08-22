from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from hydra.chaos.injector import ChaosInjector
from hydra.dashboard import start_server, watch_tick
from hydra.factory import HydraApp
from hydra.live_snapshot import (
    _break_state,
    build_snapshot,
    infer_loop,
    read_snapshot,
    write_snapshot,
)


@pytest.mark.asyncio
async def test_snapshot_keeps_last_good_amazon_products(app):
    ok = await app.ingest("amazon_products")
    assert ok.status == "ok"
    write_snapshot(app)
    first = read_snapshot(app.live_path)
    assert first is not None
    assert len(first["products_good"]) >= 8

    app.break_source("amazon_products", "volume_collapse", keep=2)
    broken = await app.ingest("amazon_products")
    assert broken.status == "failed"
    snap = read_snapshot(app.live_path)
    assert snap["serving"] == "last-known-good"
    assert len(snap["products_good"]) >= 8
    assert len(snap["products"]) >= 8
    assert len(snap["products_now"]) <= 2
    assert snap["health"] in {"degraded", "circuit_open"}
    view = snap["break_view"]
    assert view["fault"] == "volume_collapse"
    assert view["state"] == "broken"
    assert any((card.get("_ui") or {}).get("ghost") for card in view["cards"])


def test_faults_round_trip_second_app(app, tmp_path):
    app.break_source("amazon_products", "http_403", permanent=True)
    raw = json.loads(app.faults_path.read_text())
    assert raw["amazon_products"]["type"] == "http_403"

    other = HydraApp(db_path=tmp_path / "second.duckdb")
    try:
        spec = other.injector.active("amazon_products")
        assert spec is not None
        assert spec["type"] == "http_403"
        assert spec.get("permanent") is True
    finally:
        other.close()


def test_injector_persist_file_load(tmp_path):
    path = tmp_path / "hydra-faults.json"
    first = ChaosInjector(persist_path=path)
    first.inject("amazon_products", "http_403")
    second = ChaosInjector(persist_path=path)
    assert second.active("amazon_products")["type"] == "http_403"


def test_healthy_scrape_does_not_freeze_on_guard():
    phase, steps = infer_loop(
        last_run={"status": "ok"},
        incident={"resolution": "open"},
        heals=[{"blocked_reason": "approval denied or timed out"}],
        pending={"status": "pending"},
        circuit="closed",
        active_fault=None,
    )
    assert phase == "idle"
    assert steps["guard"] != "current"
    assert (
        _break_state(
            active_fault=None,
            last_run={"status": "ok"},
            incident={"resolution": "healed"},
            circuit="closed",
            pending={"status": "pending"},
        )
        == "healed"
    )


@pytest.mark.asyncio
async def test_watch_tick_recovers_three_breaks_without_guard(app):
    app.prepare_demo("amazon_products")
    await app.ingest("amazon_products")
    for fault, cfg in (
        ("http_403", {"once": True}),
        ("volume_collapse", {"keep": 2, "once": True}),
        ("null_flood", {"field": "price", "rate": 0.6, "once": True}),
    ):
        app.break_source("amazon_products", fault, **cfg)
        snap = await watch_tick(app, "amazon_products")
        assert snap["circuit_state"] == "closed", fault
        assert snap["phase"] != "guard", fault
        assert snap.get("break_view", {}).get("state") in {"healed", "idle"}, fault


@pytest.mark.asyncio
async def test_watch_tick_heals_amazon_403(app):
    await app.ingest("amazon_products")
    app.break_source("amazon_products", "http_403")
    snap = await watch_tick(app, "amazon_products")
    assert snap["health"] == "healthy"
    assert snap.get("last_resolutions") == ["healed"]
    heals = app.store.query(
        "SELECT primitive, verification_passed FROM heal_ledger WHERE source_id = ?",
        ["amazon_products"],
    )
    assert any(row["verification_passed"] for row in heals)
    rel = snap.get("reliability") or {}
    assert rel.get("incidents", 0) >= 1
    assert rel.get("incidents_healed", 0) >= 1
    assert rel.get("heal_attempts", 0) >= 1
    assert rel.get("heal_success_pct") == 100.0
    assert rel.get("mttr_last_s") is not None


@pytest.mark.asyncio
async def test_dashboard_http_live_and_html(app, monkeypatch):
    monkeypatch.setenv("HYDRA_DASHBOARD_QUIET", "1")
    monkeypatch.setenv("HYDRA_DASHBOARD_TOKEN", "")
    await app.ingest("amazon_products")
    write_snapshot(app)
    server, stop, _ = start_server(
        host="127.0.0.1",
        port=0,
        watch=False,
        app=app,
        live_path=app.live_path,
        faults_path=app.faults_path,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    try:
        html_res = urllib.request.urlopen(f"{base}/", timeout=5)
        assert html_res.status == 200
        html = html_res.read().decode()
        assert "HYDRA" in html
        assert "Amazon catalog reliability" in html
        assert "Sruthi Anuvalasetty" in html
        assert "Ramachandra Nalam" in html
        assert "https://www.linkedin.com/in/sruthi-anuvalasetty/" in html
        assert "https://www.linkedin.com/in/ramachandra-nalam/" in html
        assert 'data-theme-set="light"' in html
        assert "hydra-theme" in html
        assert "--font-serif" in html
        assert "Source Serif 4" in html
        assert "a:visited" in html
        assert "showMissing" in html
        assert "This scrape (held back" in html
        assert "MTTD" in html
        assert "MTTR" in html
        assert "Heal success" in html
        assert "False-heal rate" in html
        assert "breakRibbon" in html
        assert "BROKE" in html
        assert "ARMED" in html

        live_res = urllib.request.urlopen(f"{base}/api/live", timeout=5)
        assert live_res.status == 200
        payload = json.loads(live_res.read().decode())
        assert payload["source_id"] == "amazon_products"
        assert payload["health"] == "healthy"
        assert len(payload["products"]) >= 8
        built = build_snapshot(app)
        assert built["health"] == payload["health"]

        req = urllib.request.Request(
            f"{base}/api/break",
            data=b'{"fault":"http_403"}',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("expected 403")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        stop.set()
        server.shutdown()


@pytest.mark.asyncio
async def test_dashboard_break_with_controls(app, monkeypatch):
    monkeypatch.setenv("HYDRA_DASHBOARD_QUIET", "1")
    monkeypatch.setenv("HYDRA_DASHBOARD_TOKEN", "")
    monkeypatch.setenv("HYDRA_DASHBOARD_CONTROLS", "1")
    await app.ingest("amazon_products")
    write_snapshot(app)
    server, stop, _ = start_server(
        host="127.0.0.1",
        port=0,
        watch=False,
        app=app,
        live_path=app.live_path,
        faults_path=app.faults_path,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
        assert "Break Amazon" in html
        for name in (
            "http_403",
            "captcha_wall",
            "volume_collapse",
            "selector_drift",
            "field_rename",
            "type_change",
            "null_flood",
            "poison_record",
        ):
            assert name in html
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/break",
            data=b'{"fault":"http_403","once":true}',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        res = urllib.request.urlopen(req, timeout=5)
        assert res.status == 200
        payload = json.loads(res.read().decode())
        assert payload["ok"] is True
        assert payload["injected"] == "http_403"
        assert app.injector.active("amazon_products")["type"] == "http_403"
    finally:
        stop.set()
        server.shutdown()


def test_replay_app_still_uses_hydra_live_sidecar(app):
    assert app.live_path.name == "hydra-live.json"
    assert app.faults_path.name == "hydra-faults.json"
    assert app.config.mode == "replay"


def test_live_dashboard_isolate_does_not_touch_replay_sidecar(tmp_path, monkeypatch):
    from hydra.dashboard_live import isolate
    from hydra.factory import HydraApp
    from hydra.live_snapshot import write_snapshot

    root = Path(__file__).resolve().parents[2]
    replay = root / "data" / "hydra-live.json"
    before = replay.read_text() if replay.is_file() else None
    monkeypatch.setenv("HYDRA_OTEL_DISABLED", "1")
    monkeypatch.setenv("HYDRA_PORT_DISABLED", "1")
    monkeypatch.setenv("HYDRA_ROOT", str(root))
    monkeypatch.setenv("HYDRA_LIVE_DB_PATH", str(tmp_path / "hydra-live.duckdb"))
    monkeypatch.setenv("HYDRA_JUDGE_LIVE_PATH", str(tmp_path / "hydra-judge.json"))
    monkeypatch.setenv("HYDRA_JUDGE_FAULTS_PATH", str(tmp_path / "hydra-judge-faults.json"))
    monkeypatch.setenv("HYDRA_DB_PATH", str(root / "hydra.duckdb"))
    monkeypatch.setenv("HYDRA_MODE", "replay")
    monkeypatch.setenv("HYDRA_LIVE_PATH", "")
    monkeypatch.setenv("HYDRA_FAULTS_PATH", "")
    monkeypatch.setenv("HYDRA_DASHBOARD_PORT", "8080")
    monkeypatch.setenv("HYDRA_DASHBOARD_INTERVAL_S", "3")

    paths = isolate()
    assert Path(paths["db"]) == tmp_path / "hydra-live.duckdb"
    assert Path(paths["live"]) == tmp_path / "hydra-judge.json"
    assert os.environ["HYDRA_MODE"] == "live"

    instance = HydraApp()
    try:
        assert instance.config.mode == "live"
        assert instance.live_path == tmp_path / "hydra-judge.json"
        assert instance.faults_path == tmp_path / "hydra-judge-faults.json"
        write_snapshot(instance)
        assert instance.live_path.is_file()
        assert json.loads(instance.live_path.read_text())["mode"] == "live"
    finally:
        instance.close()

    after = replay.read_text() if replay.is_file() else None
    assert after == before
    assert not (tmp_path / "hydra-live.json").exists()


@pytest.mark.asyncio
async def test_live_dashboard_http_label_and_isolation(tmp_path, monkeypatch):
    from hydra.dashboard import start_server
    from hydra.dashboard_live import isolate
    from hydra.factory import HydraApp
    from hydra.live_snapshot import write_snapshot

    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("HYDRA_DASHBOARD_QUIET", "1")
    monkeypatch.setenv("HYDRA_DASHBOARD_TOKEN", "")
    monkeypatch.setenv("HYDRA_DASHBOARD_CONTROLS", "1")
    monkeypatch.setenv("HYDRA_OTEL_DISABLED", "1")
    monkeypatch.setenv("HYDRA_PORT_DISABLED", "1")
    monkeypatch.setenv("HYDRA_ROOT", str(root))
    monkeypatch.setenv("HYDRA_LIVE_DB_PATH", str(tmp_path / "hydra-live.duckdb"))
    monkeypatch.setenv("HYDRA_JUDGE_LIVE_PATH", str(tmp_path / "hydra-judge.json"))
    monkeypatch.setenv("HYDRA_JUDGE_FAULTS_PATH", str(tmp_path / "hydra-judge-faults.json"))
    monkeypatch.setenv("HYDRA_LIVE_PATH", "")
    monkeypatch.setenv("HYDRA_FAULTS_PATH", "")
    isolate()
    # Serve isolated live files without calling Bright Data (watch=False).
    instance = HydraApp()
    try:
        write_snapshot(instance)
        server, stop, _ = start_server(
            host="127.0.0.1",
            port=0,
            watch=False,
            app=instance,
            live_path=instance.live_path,
            faults_path=instance.faults_path,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
            assert "HYDRA" in html
            assert "live Bright Data" in html
            assert "Amazon catalog reliability" in html
            live = json.loads(
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/live", timeout=5).read().decode()
            )
            assert live["mode"] == "live"
            assert live["source_id"] == "amazon_products"
        finally:
            stop.set()
            server.shutdown()
    finally:
        instance.close()
    assert instance.live_path.name == "hydra-judge.json"
