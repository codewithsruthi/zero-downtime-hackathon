"""Atomic live snapshot for the public HYDRA dashboard.

Never writes ``data/latest.json`` (INV-1). Sidecar is ``data/hydra-live.json``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BREAK_COPY = {
    "http_403": {
        "mode": "blocked",
        "armed": "HTTP 403 armed. Next scrape will be blocked.",
        "broken": "Scrape blocked (HTTP 403). Catalog is last-good, not promoted.",
        "healed": "Scrape unblocked. Live catalog restored.",
    },
    "captcha_wall": {
        "mode": "captcha",
        "armed": "Captcha wall armed. Next scrape will return a human-check page.",
        "broken": "Captcha wall. Extractor got HTML, not products.",
        "healed": "Captcha bypassed. Live catalog restored.",
    },
    "volume_collapse": {
        "mode": "volume",
        "armed": "Volume collapse armed. Next scrape will return too few products.",
        "broken": "Volume collapse. Only a handful of products came back.",
        "healed": "Volume restored to a full catalog.",
    },
    "selector_drift": {
        "mode": "drift",
        "armed": "Selector drift armed. Next extract should match 0 products.",
        "broken": "Selector drift. Extractor matched 0 products.",
        "healed": "Extractor recovered a full catalog.",
    },
    "field_rename": {
        "mode": "rename",
        "armed": "Price field rename armed. Next scrape will lose price.",
        "broken": "Price field renamed away. Cards show missing prices.",
        "healed": "Price field mapped back. Dollars restored.",
    },
    "type_change": {
        "mode": "types",
        "armed": "Type-change armed. Some prices will become the string n/a.",
        "broken": "Some prices are strings (n/a), not numbers. Bad rows held back.",
        "healed": "Invalid price rows quarantined / catalog rebuilt.",
    },
    "null_flood": {
        "mode": "nulls",
        "armed": "Null-price flood armed. Most prices will be wiped.",
        "broken": "Most prices are null. Cards below are this scrape, not promoted.",
        "healed": "Prices restored from a good scrape.",
    },
    "poison_record": {
        "mode": "poison",
        "armed": "Poison row armed. One product will fail to load.",
        "broken": "One poisoned product. That row is not promoted.",
        "healed": "Poisoned row quarantined. Remaining catalog is live.",
    },
}

AMAZON = "amazon_products"
STEPS = ("detect", "classify", "guard", "act", "verify")
LIVE_NAME = "hydra-live.json"
FAULTS_NAME = "hydra-faults.json"


def data_dir_for(app) -> Path:
    return Path(getattr(app, "data_dir"))


def live_path_for(app) -> Path:
    return Path(getattr(app, "live_path", data_dir_for(app) / LIVE_NAME))


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    tmp.replace(path)


def read_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_derived_products(store, source_id: str = AMAZON) -> list[dict[str, Any]]:
    table = store.derived_table(source_id)
    try:
        rows = store.query(f'SELECT * FROM "{table}"')
    except Exception:
        return []
    out = []
    for row in rows:
        if set(row.keys()) <= {"_empty"}:
            continue
        out.append(jsonable(row))
    return out


def _row(store, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    try:
        rows = store.query(sql, params or [])
    except Exception:
        return None
    return jsonable(rows[0]) if rows else None


def _rows(store, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    try:
        rows = store.query(sql, params or [])
    except Exception:
        return []
    return [jsonable(r) for r in rows]


def infer_loop(
    *,
    last_run: dict[str, Any] | None,
    incident: dict[str, Any] | None,
    heals: list[dict[str, Any]],
    pending: dict[str, Any] | None,
    circuit: str,
    active_fault: dict[str, Any] | None,
) -> tuple[str, dict[str, str]]:
    steps = {name: "idle" for name in STEPS}
    circuit = circuit or "closed"
    status = (last_run or {}).get("status")
    resolution = (incident or {}).get("resolution")

    if circuit == "open":
        steps["detect"] = "done"
        steps["classify"] = "done"
        steps["guard"] = "current"
        return "guard", steps

    # A healthy scrape means the catalog already recovered. Do not freeze on
    # Guard because of a leftover approval row or an open incident.
    if status in {"ok", "healed"} and not active_fault:
        if resolution == "healed":
            for name in STEPS:
                steps[name] = "done"
            return "idle", steps
        return "idle", steps

    if pending:
        steps["detect"] = "done"
        steps["classify"] = "done"
        steps["guard"] = "current"
        return "guard", steps

    if resolution == "open":
        steps["detect"] = "done"
        steps["classify"] = "done"
        verified = [h for h in heals if h.get("verification_passed")]
        blocked = [h for h in heals if h.get("blocked_reason")]
        unfinished = [
            h
            for h in heals
            if h.get("verification_passed") is None and not h.get("blocked_reason")
        ]
        if unfinished or (heals and not verified and not blocked):
            steps["guard"] = "done"
            steps["act"] = "current"
            return "act", steps
        if blocked and not verified:
            steps["guard"] = "current"
            return "guard", steps
        steps["guard"] = "done"
        steps["act"] = "done"
        steps["verify"] = "current"
        return "verify", steps

    if status == "failed":
        steps["detect"] = "done"
        steps["classify"] = "current"
        return "classify", steps

    if active_fault:
        steps["detect"] = "current"
        return "detect", steps

    if resolution == "healed":
        for name in STEPS:
            steps[name] = "done"
        return "idle", steps

    return "idle", steps


def _raw_records(store, source_id: str) -> list[dict[str, Any]]:
    latest = None
    try:
        latest = store.latest_raw(source_id)
    except Exception:
        return []
    if not latest:
        return []
    try:
        data = json.loads(latest.get("payload") or "")
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get("data") if isinstance(data.get("data"), list) else [data]
    if not isinstance(data, list):
        return []
    return [jsonable(row) for row in data if isinstance(row, dict)]


def _card(row: dict[str, Any], **flags: Any) -> dict[str, Any]:
    out = dict(row)
    ui = {key: val for key, val in flags.items() if val}
    if ui:
        out["_ui"] = ui
    return jsonable(out)


def _infer_fault(
    active_fault: dict[str, Any] | None,
    last_run: dict[str, Any] | None,
    failed_assertions: list[str],
    prev_view: dict[str, Any] | None,
) -> str | None:
    if active_fault and active_fault.get("type"):
        return str(active_fault["type"])
    if prev_view and prev_view.get("fault"):
        return str(prev_view["fault"])
    run = last_run or {}
    err = run.get("error_type") or ""
    if run.get("http_status") == 403 and err == "HTTPError":
        return "http_403"
    if err == "CaptchaBlocked":
        return "captcha_wall"
    if err == "ConversionError":
        return "poison_record"
    if "row_count_floor" in failed_assertions:
        return "volume_collapse"
    if "in_stock_price" in failed_assertions:
        return "null_flood"
    if (run.get("rows_in") or 0) == 0 and run.get("status") == "failed":
        return "selector_drift"
    if (run.get("schema_errors") or 0) > 0:
        return "type_change"
    return None


def build_break_view(
    *,
    fault: str | None,
    state: str,
    last_run: dict[str, Any] | None,
    products_now: list[dict[str, Any]],
    products_good: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    failed_assertions: list[str],
    heals: list[dict[str, Any]],
    incident: dict[str, Any] | None,
) -> dict[str, Any]:
    copy = BREAK_COPY.get(fault or "", {})
    mode = copy.get("mode") or "live"
    headline = copy.get(state) or (
        "Amazon catalog is live." if state == "idle" else f"{state} · {fault or 'catalog'}"
    )
    run = last_run or {}
    priced_now = sum(1 for row in products_now if row.get("price") not in (None, ""))
    healed_by = next(
        (
            str(row.get("primitive"))
            for row in reversed(heals)
            if row.get("verification_passed")
        ),
        None,
    )
    detail_bits = []
    if run:
        detail_bits.append(
            f"last run {run.get('status') or '—'} · rows {run.get('rows_in') or 0}→{run.get('rows_out') or 0}"
            + (f" · http {run.get('http_status')}" if run.get("http_status") else "")
            + (f" · {run.get('error_type')}" if run.get("error_type") else "")
        )
    if failed_assertions:
        detail_bits.append("failed " + ", ".join(failed_assertions))
    if incident and incident.get("failure_class"):
        detail_bits.append(f"class {incident.get('failure_class')}")
    if healed_by:
        detail_bits.append(f"via {healed_by}")
    cards = _break_cards(
        fault=fault,
        state=state,
        products_now=products_now,
        products_good=products_good,
        raw_rows=raw_rows,
    )
    return {
        "fault": fault,
        "state": state,
        "mode": mode if state != "idle" else "live",
        "headline": headline,
        "detail": " · ".join(detail_bits),
        "healed_by": healed_by,
        "failure_class": (incident or {}).get("failure_class"),
        "metrics": {
            "rows_now": len(products_now),
            "rows_good": len(products_good),
            "priced_now": priced_now,
            "rejected": int(run.get("rows_rejected") or 0),
            "http_status": run.get("http_status"),
        },
        "cards": cards,
    }


def _break_cards(
    *,
    fault: str | None,
    state: str,
    products_now: list[dict[str, Any]],
    products_good: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if state in {"idle", "healed"} or not fault:
        return [_card(row) for row in (products_now or products_good)]
    good = products_good or []
    now = products_now or []
    if fault in {"http_403", "captcha_wall"}:
        return [_card(row, dimmed=True, blocked=fault == "http_403", captcha=fault == "captcha_wall") for row in good]
    if fault == "volume_collapse":
        now_ids = {row.get("asin") for row in now}
        cards = [_card(row) for row in now]
        for row in good:
            if row.get("asin") not in now_ids:
                cards.append(_card(row, ghost=True))
        return cards
    if fault == "selector_drift":
        if now:
            return [_card(row, ghost=True) for row in now]
        return [_card(row, ghost=True) for row in good]
    if fault == "null_flood":
        return [_card(row, missing_price=row.get("price") in (None, "")) for row in (now or good)]
    if fault == "field_rename":
        by_asin = {row.get("asin"): row for row in raw_rows if row.get("asin")}
        source = now or good
        cards = []
        for row in source:
            raw = by_asin.get(row.get("asin"), {})
            renamed = "price" not in raw and ("amt" in raw or "current_price" in raw)
            cards.append(
                _card(
                    {**row, "price": row.get("price")},
                    missing_price=row.get("price") in (None, ""),
                    renamed=renamed,
                )
            )
        if not cards and raw_rows:
            for raw in raw_rows:
                cards.append(
                    _card(
                        {**raw, "price": raw.get("price", raw.get("amt", raw.get("current_price")))},
                        missing_price=True,
                        renamed=True,
                    )
                )
        return cards
    if fault == "type_change":
        by_asin = {row.get("asin"): row for row in raw_rows if row.get("asin")}
        if raw_rows:
            cards = []
            loaded = {row.get("asin") for row in now}
            for raw in raw_rows:
                price = raw.get("price")
                typed = isinstance(price, str)
                dropped = raw.get("asin") not in loaded
                cards.append(
                    _card(
                        {**raw, "price": price if typed else raw.get("price")},
                        typed=typed,
                        missing_price=price in (None, "") or typed,
                        ghost=dropped and not typed,
                    )
                )
            return cards
        return [_card(row, typed=isinstance(row.get("price"), str)) for row in now or good]
    if fault == "poison_record":
        poison_asins = {
            row.get("asin")
            for row in raw_rows
            if row.get("_poison") or row.get("_invalid_utf8")
        }
        cards = [_card(row, poison=row.get("asin") in poison_asins) for row in (now or good)]
        for raw in raw_rows:
            if raw.get("asin") in poison_asins and not any(c.get("asin") == raw.get("asin") for c in cards):
                cards.append(_card(raw, poison=True))
        if poison_asins and not any(c.get("_ui", {}).get("poison") for c in cards) and good:
            # Fallback: mark the 5th last-good card (default at=4).
            idx = 4 if len(good) > 4 else 0
            cards = [_card(row, poison=(i == idx)) for i, row in enumerate(good)]
        return cards
    return [_card(row) for row in (now or good)]


def _break_state(
    *,
    active_fault: dict[str, Any] | None,
    last_run: dict[str, Any] | None,
    incident: dict[str, Any] | None,
    circuit: str,
    pending: dict[str, Any] | None,
) -> str:
    status = (last_run or {}).get("status")
    resolution = (incident or {}).get("resolution")
    if circuit == "open" and status == "failed":
        return "broken"
    if status in {"ok", "healed"} and not active_fault:
        if resolution == "healed":
            return "healed"
        return "idle"
    if circuit == "open" or pending:
        return "broken"
    if status == "failed":
        return "broken"
    if active_fault:
        return "armed"
    if resolution == "healed" and status in {"ok", "healed", None}:
        return "healed"
    if resolution == "open":
        return "broken"
    return "idle"


def _banner(health: str, serving: str, phase: str, last_run: dict[str, Any] | None) -> str:
    if health == "circuit_open" or (
        phase == "guard" and (last_run or {}).get("status") == "ok"
    ):
        return (
            "Guard stopped further heals (budget used or the same 403 repeated). "
            "This is designed, not a hang. Click Reset circuit, then Break again. "
            "A single heal is usually 1–6 seconds."
        )
    if serving == "last-known-good":
        err = (last_run or {}).get("error_type") or "assertion failure"
        return (
            f"Pipeline {health}. Cards show this scrape ({err}) — not promoted. "
            "Last-good is held until Verify. Healing is in progress."
        )
    if phase == "detect":
        return "Fault armed. Next ingest will trip Detect."
    if health == "healthy":
        return "Amazon catalog is live. Last-good payload is what you see."
    return f"Source health is {health}."


def build_snapshot(app, *, source_id: str = AMAZON) -> dict[str, Any]:
    store = app.store
    prev = read_snapshot(live_path_for(app)) or {}
    state = store.get_source_state(source_id) or {}
    last_run = _row(
        store,
        """
        SELECT * FROM pipeline_run
        WHERE source_id = ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        [source_id],
    )
    incident = _row(
        store,
        """
        SELECT * FROM incident
        WHERE source_id = ?
        ORDER BY detected_at DESC
        LIMIT 1
        """,
        [source_id],
    )
    heals: list[dict[str, Any]] = []
    if incident:
        heals = _rows(
            store,
            """
            SELECT primitive, attempt, autonomy_tier, verification_passed,
                   notes, blocked_reason, started_at, ended_at, approved_by
            FROM heal_ledger
            WHERE incident_id = ?
            ORDER BY attempt
            """,
            [incident["incident_id"]],
        )
    pending = _row(
        store,
        """
        SELECT * FROM pending_approval
        WHERE source_id = ? AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [source_id],
    )
    failed_assertions = []
    if last_run:
        failed_assertions = [
            row["assertion_id"]
            for row in _rows(
                store,
                """
                SELECT assertion_id FROM assertion_result
                WHERE run_id = ? AND passed = FALSE
                """,
                [last_run["run_id"]],
            )
        ]
    products_now = list_derived_products(store, source_id)
    run_ok = bool(last_run and last_run.get("status") in {"ok", "healed"})
    prev_good = prev.get("products_good") or prev.get("products") or []
    if run_ok and products_now:
        products_good = products_now
    elif prev_good:
        products_good = prev_good
    else:
        products_good = products_now

    health = state.get("health") or ("healthy" if run_ok or not last_run else "degraded")
    circuit = state.get("circuit_state") or "closed"
    if circuit == "open":
        health = "circuit_open"
    serving = "live" if run_ok or not last_run else "last-known-good"
    injector = getattr(app, "injector", None)
    if injector is not None and hasattr(injector, "load"):
        injector.load()
    active_fault = injector.active(source_id) if injector is not None else None
    phase, steps = infer_loop(
        last_run=last_run,
        incident=incident,
        heals=heals,
        pending=pending,
        circuit=circuit,
        active_fault=active_fault,
    )
    try:
        board = jsonable(store.scoreboard())
    except Exception:
        board = {"by_class": [], "autonomy_pct": None, "incidents": []}
    try:
        contract = app.contracts.get(source_id)
        budget = int((contract.get("healing") or {}).get("heal_budget_per_hour") or 5)
    except Exception:
        budget = 5
    try:
        reliability = jsonable(store.reliability_metrics(source_id, budget=budget))
    except Exception:
        reliability = {}
    sources = _rows(store, "SELECT * FROM source_state")
    try:
        from hydra.port_rest import port_configured
        from hydra.signoz_rest import instance_url, signoz_configured

        links = {
            "port": "https://app.getport.io" if port_configured() else None,
            "signoz": instance_url() if signoz_configured() else None,
        }
    except Exception:
        links = {"port": None, "signoz": None}

    products = products_good if serving == "last-known-good" else products_now
    raw_rows = _raw_records(store, source_id)
    prev_view = prev.get("break_view") if isinstance(prev.get("break_view"), dict) else None
    fault = _infer_fault(active_fault, last_run, failed_assertions, prev_view)
    break_state = _break_state(
        active_fault=active_fault,
        last_run=last_run,
        incident=incident,
        circuit=circuit,
        pending=pending,
    )
    if break_state == "idle" and prev_view and prev_view.get("state") == "healed":
        break_state = "healed"
        fault = fault or prev_view.get("fault")
    break_view = build_break_view(
        fault=fault,
        state=break_state,
        last_run=last_run,
        products_now=products_now,
        products_good=products_good,
        raw_rows=raw_rows,
        failed_assertions=failed_assertions,
        heals=heals,
        incident=incident,
    )
    banner = break_view["headline"] if break_state != "idle" else _banner(
        health, serving, phase, last_run
    )
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mode": getattr(getattr(app, "config", None), "mode", "replay"),
        "source_id": source_id,
        "health": health,
        "circuit_state": circuit,
        "serving": serving,
        "banner": banner,
        "phase": phase,
        "steps": steps,
        "active_fault": jsonable(active_fault),
        "break_view": break_view,
        "last_run": last_run,
        "incident": incident,
        "heals": heals,
        "pending_approval": pending,
        "failed_assertions": failed_assertions,
        "products": products,
        "products_now": products_now,
        "products_good": products_good,
        "scoreboard": board,
        "reliability": reliability,
        "sources": sources,
        "links": links,
        "practice": "self-healing",
    }


def write_snapshot(app, *, source_id: str = AMAZON) -> dict[str, Any]:
    try:
        payload = build_snapshot(app, source_id=source_id)
        atomic_write_json(live_path_for(app), payload)
        return payload
    except Exception:
        return read_snapshot(live_path_for(app)) or {}


def patch_snapshot_fault(
    path: Path, source_id: str, fault: dict[str, Any] | None
) -> dict[str, Any]:
    snap = read_snapshot(path) or {
        "source_id": source_id,
        "health": "healthy",
        "circuit_state": "closed",
        "serving": "live",
        "phase": "detect" if fault else "idle",
        "steps": {name: "idle" for name in STEPS},
        "products": [],
        "products_good": [],
        "products_now": [],
        "heals": [],
        "practice": "self-healing",
    }
    snap["active_fault"] = jsonable(fault)
    snap["updated_at"] = datetime.now(timezone.utc).isoformat()
    if fault:
        snap["phase"] = "detect"
        steps = dict(snap.get("steps") or {name: "idle" for name in STEPS})
        steps["detect"] = "current"
        snap["steps"] = steps
        view = build_break_view(
            fault=str(fault.get("type") or ""),
            state="armed",
            last_run=snap.get("last_run"),
            products_now=snap.get("products_now") or [],
            products_good=snap.get("products_good") or snap.get("products") or [],
            raw_rows=[],
            failed_assertions=snap.get("failed_assertions") or [],
            heals=snap.get("heals") or [],
            incident=snap.get("incident"),
        )
        snap["break_view"] = view
        snap["banner"] = view["headline"]
    atomic_write_json(path, snap)
    return snap


def empty_snapshot(source_id: str = AMAZON) -> dict[str, Any]:
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "replay",
        "source_id": source_id,
        "health": "waiting",
        "circuit_state": "closed",
        "serving": "empty",
        "banner": "Waiting for the first Amazon ingest. Run scrape or start the dashboard with --watch.",
        "phase": "idle",
        "steps": {name: "idle" for name in STEPS},
        "active_fault": None,
        "break_view": {
            "fault": None,
            "state": "idle",
            "mode": "live",
            "headline": "",
            "detail": "",
            "cards": [],
        },
        "last_run": None,
        "incident": None,
        "heals": [],
        "pending_approval": None,
        "failed_assertions": [],
        "products": [],
        "products_now": [],
        "products_good": [],
        "scoreboard": {"by_class": [], "autonomy_pct": None, "incidents": []},
        "reliability": {},
        "sources": [],
        "links": {"port": None, "signoz": None},
        "practice": "self-healing",
    }
