from __future__ import annotations

from typing import Any

from hydra.port_rest import delete_entity, port_configured, upsert_blueprint, upsert_entity
from hydra.port_setup.blueprints import BLUEPRINTS

SEED_SOURCES = ("gh_trending_repos", "crypto_prices_api", "city_open_data")
AMAZON = "amazon_products"
PRODUCT_BLUEPRINT = next(b for b in BLUEPRINTS if b["identifier"] == "hydra_product")
SOURCE_URLS = {
    "amazon_products": "https://brightdata.com/cp/datasets/browse/gd_l7q7dkf244hwjntr0",
    "gh_trending_repos": "https://github.com/trending",
    "crypto_prices_api": "https://example.test/crypto/prices",
    "city_open_data": "https://example.test/cities.csv",
}


def _duration_ms(run: dict[str, Any]) -> int:
    started, ended = run.get("started_at"), run.get("ended_at")
    if not started or not ended:
        return 0
    return max(0, int((ended - started).total_seconds() * 1000))


def sync_source(app, source_id: str) -> dict[str, Any]:
    if not port_configured():
        return {"skipped": True, "source_id": source_id}
    try:
        return _sync_source(app, source_id)
    except Exception as exc:
        return {"source_id": source_id, "error": str(exc)[:200]}


def _sync_source(app, source_id: str) -> dict[str, Any]:
    contract = app.contracts.get(source_id)
    state = app.store.get_source_state(source_id) or {}
    runs = app.store.query(
        """
        SELECT * FROM pipeline_run
        WHERE source_id = ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        [source_id],
    )
    run = runs[0] if runs else None
    table = app.store.derived_table(source_id)
    try:
        rows = app.store.query(f'SELECT COUNT(*) AS n FROM "{table}"')
        rows_out = int(rows[0]["n"]) if rows else int((run or {}).get("rows_out") or 0)
    except Exception:
        rows_out = int((run or {}).get("rows_out") or 0)
    freshness = app.store.seconds_since_success(source_id)
    heals = app.store.query(
        """
        SELECT COUNT(*) AS n FROM heal_ledger
        WHERE source_id = ? AND verification_passed = TRUE
          AND started_at > CURRENT_TIMESTAMP - INTERVAL 7 DAY
        """,
        [source_id],
    )
    args = (contract.get("acquisition") or {}).get("primary", {}).get("args") or {}
    url = SOURCE_URLS.get(source_id) or args.get("url") or args.get("dataset_id") or "https://example.test"
    upsert_entity(
        "hydra_source",
        source_id,
        {
            "kind": contract["acquisition"]["kind"],
            "url": url if str(url).startswith("http") else SOURCE_URLS.get(source_id, "https://example.test"),
            "contract_version": int(contract.get("contract_version", 1)),
            "health": state.get("health") or "healthy",
            "circuit_state": state.get("circuit_state") or "closed",
            "freshness_seconds": round(freshness) if freshness == freshness else 0,
            "freshness_slo_seconds": contract["acquisition"]["freshness_slo_seconds"],
            "acquisition_rung": int(state.get("current_rung") or 0),
            "autonomy_tier_max": int(contract["healing"]["max_autonomy_tier"]),
            "assertion_count": len(contract["assertions"]),
            "last_run_status": (run or {}).get("status") or "unknown",
            "heals_last_7d": int(heals[0]["n"]) if heals else 0,
            "owner_team": contract.get("owner_team") or "data-platform",
        },
    )
    if run:
        upsert_entity(
            "hydra_run",
            run["run_id"],
            {
                "status": run["status"],
                "rows_in": int(run["rows_in"] or 0),
                "rows_out": rows_out,
                "duration_ms": _duration_ms(run),
                "trace_id": run.get("trace_id") or "",
            },
            relations={"source": source_id},
        )
    return {
        "source_id": source_id,
        "health": state.get("health") or "healthy",
        "last_run": (run or {}).get("status"),
        "run_id": (run or {}).get("run_id"),
        "rows": rows_out,
        "trace_id": (run or {}).get("trace_id"),
    }


def sync_incidents(app, source_id: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
    if not port_configured():
        return []
    try:
        return _sync_incidents(app, source_id, limit)
    except Exception:
        return []


def _sync_incidents(app, source_id: str | None, limit: int) -> list[dict[str, Any]]:
    sql = "SELECT * FROM incident ORDER BY detected_at DESC LIMIT ?"
    args: list[Any] = [limit]
    if source_id:
        sql = "SELECT * FROM incident WHERE source_id = ? ORDER BY detected_at DESC LIMIT ?"
        args = [source_id, limit]
    incidents = app.store.query(sql, args)
    out = []
    for inc in incidents:
        props = {
            "failure_class": inc["failure_class"],
            "fingerprint": inc["fingerprint"],
            "detected_at": inc["detected_at"].isoformat()
            if hasattr(inc["detected_at"], "isoformat")
            else str(inc["detected_at"]),
            "resolution": inc["resolution"],
            "attempts": int(inc["attempts"] or 0),
            "trace_id": inc.get("trace_id") or "",
        }
        if inc.get("resolved_at"):
            props["resolved_at"] = (
                inc["resolved_at"].isoformat()
                if hasattr(inc["resolved_at"], "isoformat")
                else str(inc["resolved_at"])
            )
        if inc.get("mttr_seconds") is not None:
            props["mttr_seconds"] = float(inc["mttr_seconds"])
        upsert_entity(
            "hydra_incident",
            inc["incident_id"],
            props,
            relations={"source": inc["source_id"]},
        )
        heals = app.store.query(
            "SELECT * FROM heal_ledger WHERE incident_id = ? ORDER BY attempt",
            [inc["incident_id"]],
        )
        for heal in heals:
            upsert_entity(
                "hydra_heal_action",
                heal["heal_id"],
                {
                    "primitive": heal["primitive"],
                    "autonomy_tier": int(heal["autonomy_tier"] or 0),
                    "attempt": int(heal["attempt"] or 0),
                    "approved_by": heal.get("approved_by") or "",
                    "verification_passed": bool(heal.get("verification_passed")),
                    "before_state": heal.get("before_state") or "",
                    "after_state": heal.get("after_state") or "",
                },
                relations={"incident": inc["incident_id"]},
            )
        out.append(inc)
    return out


def sync_catalog(app, source_id: str | None = None) -> list[dict[str, Any]]:
    ids = [source_id] if source_id else list(app.contracts.ids())
    summaries = [sync_source(app, sid) for sid in ids]
    for sid in ids:
        sync_incidents(app, sid)
    return summaries


def hide_seed_sources() -> None:
    if not port_configured():
        return
    for source_id in SEED_SOURCES:
        try:
            delete_entity("hydra_source", source_id)
        except Exception:
            continue


def list_amazon_products(app) -> list[dict[str, Any]]:
    table = app.store.derived_table(AMAZON)
    try:
        return app.store.query(
            f"""
            SELECT asin, title, price, currency, rating, availability, url
            FROM "{table}"
            """
        )
    except Exception:
        return []


def sync_amazon_products(app) -> list[dict[str, Any]]:
    products = list_amazon_products(app)
    if not port_configured():
        return products
    try:
        upsert_blueprint(PRODUCT_BLUEPRINT)
    except Exception:
        pass
    for row in products:
        asin = str(row.get("asin") or "").strip()
        title = str(row.get("title") or "").strip()
        if not asin or not title:
            continue
        props: dict[str, Any] = {"asin": asin, "title": title}
        if row.get("price") is not None:
            try:
                props["price"] = float(row["price"])
            except (TypeError, ValueError):
                pass
        if row.get("currency"):
            props["currency"] = str(row["currency"])
        if row.get("rating") is not None:
            try:
                props["rating"] = float(row["rating"])
            except (TypeError, ValueError):
                pass
        if row.get("availability"):
            props["availability"] = str(row["availability"])
        url = row.get("url")
        if url and str(url).startswith("http"):
            props["url"] = str(url)
        try:
            upsert_entity("hydra_product", asin, props, relations={"source": AMAZON})
        except Exception:
            continue
    return products
