#!/usr/bin/env python3
"""Push the latest Amazon scrape into Port as hydra_source + hydra_run."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hydra.factory import HydraApp
from hydra.port_rest import get_entity, upsert_entity


SOURCE_ID = "amazon_products"
DATASET_URL = "https://brightdata.com/cp/datasets/browse/gd_l7q7dkf244hwjntr0"


def _duration_ms(run: dict) -> int:
    started, ended = run.get("started_at"), run.get("ended_at")
    if not started or not ended:
        return 0
    return max(0, int((ended - started).total_seconds() * 1000))


def main() -> int:
    app = HydraApp()
    try:
        contract = app.contracts.get(SOURCE_ID)
        state = app.store.get_source_state(SOURCE_ID) or {}
        runs = app.store.query(
            """
            SELECT * FROM pipeline_run
            WHERE source_id = ? AND status = 'ok'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            [SOURCE_ID],
        )
        if not runs:
            print("no successful amazon_products run in DuckDB; scrape first")
            return 1
        run = runs[0]
        rows = app.store.query(f'SELECT COUNT(*) AS n FROM "{app.store.derived_table(SOURCE_ID)}"')
        rows_out = int(rows[0]["n"]) if rows else int(run["rows_out"] or 0)
        freshness = app.store.seconds_since_success(SOURCE_ID)
        heals = app.store.query(
            """
            SELECT COUNT(*) AS n FROM heal_ledger
            WHERE source_id = ? AND verification_passed = TRUE
              AND started_at > CURRENT_TIMESTAMP - INTERVAL 7 DAY
            """,
            [SOURCE_ID],
        )
        upsert_entity(
            "hydra_source",
            SOURCE_ID,
            {
                "kind": contract["acquisition"]["kind"],
                "url": DATASET_URL,
                "contract_version": int(contract.get("contract_version", 1)),
                "health": state.get("health") or "healthy",
                "circuit_state": state.get("circuit_state") or "closed",
                "freshness_seconds": round(freshness),
                "freshness_slo_seconds": contract["acquisition"]["freshness_slo_seconds"],
                "acquisition_rung": int(state.get("current_rung") or 0),
                "autonomy_tier_max": int(contract["healing"]["max_autonomy_tier"]),
                "assertion_count": len(contract["assertions"]),
                "last_run_status": run["status"],
                "heals_last_7d": int(heals[0]["n"]) if heals else 0,
                "owner_team": contract.get("owner_team") or "data-platform",
            },
        )
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
            relations={"source": SOURCE_ID},
        )
        source = get_entity("hydra_source", SOURCE_ID)
        props = (source.get("entity") or source).get("properties") or source.get("properties") or {}
        print(
            f"port hydra_source={SOURCE_ID} health={props.get('health')} "
            f"last_run={props.get('last_run_status')} run={run['run_id']} rows={rows_out}"
        )
        return 0
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
