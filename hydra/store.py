from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from hydra.clock import now
from hydra.ids import new_id, require_slug

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_snapshot (
    snapshot_id      VARCHAR PRIMARY KEY,
    source_id        VARCHAR NOT NULL,
    run_id           VARCHAR NOT NULL,
    fetched_at       TIMESTAMP NOT NULL,
    acquisition_rung INTEGER NOT NULL,
    capability_used  VARCHAR NOT NULL,
    url              VARCHAR,
    http_status      INTEGER,
    media_type       VARCHAR,
    content_hash     VARCHAR NOT NULL,
    content_bytes    BIGINT,
    payload          VARCHAR NOT NULL,
    trace_id         VARCHAR,
    expected_rows    VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_raw_source_time ON raw_snapshot(source_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_hash        ON raw_snapshot(content_hash);

CREATE TABLE IF NOT EXISTS pipeline_run (
    run_id           VARCHAR PRIMARY KEY,
    source_id        VARCHAR NOT NULL,
    contract_version INTEGER NOT NULL,
    started_at       TIMESTAMP NOT NULL,
    ended_at         TIMESTAMP,
    status           VARCHAR NOT NULL,
    rows_in          INTEGER DEFAULT 0,
    rows_out         INTEGER DEFAULT 0,
    rows_rejected    INTEGER DEFAULT 0,
    schema_errors    INTEGER DEFAULT 0,
    stage            VARCHAR,
    span_status      VARCHAR,
    http_status      INTEGER,
    error_type       VARCHAR,
    error_signature  VARCHAR,
    trace_id         VARCHAR
);

CREATE TABLE IF NOT EXISTS assertion_result (
    run_id       VARCHAR NOT NULL,
    source_id    VARCHAR NOT NULL,
    assertion_id VARCHAR NOT NULL,
    severity     VARCHAR NOT NULL,
    passed       BOOLEAN NOT NULL,
    observed     VARCHAR,
    evaluated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS dead_letter (
    dlq_id         VARCHAR PRIMARY KEY,
    source_id      VARCHAR NOT NULL,
    run_id         VARCHAR NOT NULL,
    record         VARCHAR NOT NULL,
    reason         VARCHAR NOT NULL,
    quarantined_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS heal_ledger (
    heal_id             VARCHAR PRIMARY KEY,
    incident_id         VARCHAR NOT NULL,
    source_id           VARCHAR NOT NULL,
    fingerprint         VARCHAR NOT NULL,
    failure_class       VARCHAR NOT NULL,
    primitive           VARCHAR NOT NULL,
    attempt             INTEGER NOT NULL,
    autonomy_tier       INTEGER NOT NULL,
    approved_by         VARCHAR,
    started_at          TIMESTAMP NOT NULL,
    ended_at            TIMESTAMP,
    verification_passed BOOLEAN,
    before_state        VARCHAR,
    after_state         VARCHAR,
    evidence_trace_id   VARCHAR,
    notes               VARCHAR,
    blocked_reason      VARCHAR
);

CREATE TABLE IF NOT EXISTS incident (
    incident_id    VARCHAR PRIMARY KEY,
    source_id      VARCHAR NOT NULL,
    fingerprint    VARCHAR NOT NULL,
    failure_class  VARCHAR NOT NULL,
    detected_at    TIMESTAMP NOT NULL,
    resolved_at    TIMESTAMP,
    mttr_seconds   DOUBLE,
    resolution     VARCHAR NOT NULL,
    attempts       INTEGER DEFAULT 0,
    trace_id       VARCHAR
);

CREATE TABLE IF NOT EXISTS heal_pattern (
    fingerprint           VARCHAR PRIMARY KEY,
    failure_class         VARCHAR NOT NULL,
    successful_primitive  VARCHAR NOT NULL,
    occurrences           INTEGER NOT NULL,
    avg_mttr_seconds      DOUBLE,
    last_at               TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS source_state (
    source_id      VARCHAR PRIMARY KEY,
    circuit_state  VARCHAR NOT NULL DEFAULT 'closed',
    current_rung   INTEGER NOT NULL DEFAULT 0,
    health         VARCHAR NOT NULL DEFAULT 'healthy',
    contract_patch VARCHAR,
    updated_at     TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_approval (
    incident_id  VARCHAR PRIMARY KEY,
    source_id    VARCHAR NOT NULL,
    primitive    VARCHAR NOT NULL,
    status       VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL
);
"""


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(self.db_path))
        self.con.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.con.close()

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        result = self.con.execute(sql, params or [])
        cols = [d[0] for d in result.description]
        return [dict(zip(cols, row)) for row in result.fetchall()]

    def derived_table(self, source_id: str) -> str:
        return f"derived_{require_slug(source_id, what='source_id')}"

    def write_raw(
        self,
        source_id: str,
        payload: str,
        *,
        run_id: str,
        rung: int,
        capability: str,
        url: str | None = None,
        http_status: int | None = 200,
        media_type: str = "text/plain",
        trace_id: str | None = None,
        expected_rows: list[dict] | None = None,
    ) -> str:
        snapshot_id = new_id("snap")
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
        self.con.execute(
            """
            INSERT INTO raw_snapshot (
                snapshot_id, source_id, run_id, fetched_at, acquisition_rung,
                capability_used, url, http_status, media_type, content_hash,
                content_bytes, payload, trace_id, expected_rows
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                snapshot_id,
                source_id,
                run_id,
                now(),
                rung,
                capability,
                url,
                http_status,
                media_type,
                digest,
                len(raw.encode("utf-8", errors="replace")),
                raw,
                trace_id,
                json.dumps(expected_rows) if expected_rows is not None else None,
            ],
        )
        return snapshot_id

    def mark_raw_expected(self, snapshot_id: str, rows: list[dict]) -> None:
        self.con.execute(
            "UPDATE raw_snapshot SET expected_rows = ? WHERE snapshot_id = ?",
            [json.dumps(rows), snapshot_id],
        )

    def latest_raw(self, source_id: str) -> dict[str, Any] | None:
        rows = self.query(
            """
            SELECT * FROM raw_snapshot
            WHERE source_id = ?
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            [source_id],
        )
        return rows[0] if rows else None

    def count_raw(self, source_id: str) -> int:
        row = self.con.execute(
            "SELECT COUNT(*) FROM raw_snapshot WHERE source_id = ?", [source_id]
        ).fetchone()
        return int(row[0]) if row else 0

    def known_good_snapshots(self, source_id: str, limit: int = 3) -> list[dict[str, Any]]:
        return self.query(
            """
            SELECT * FROM raw_snapshot
            WHERE source_id = ? AND expected_rows IS NOT NULL
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            [source_id, limit],
        )

    def latest_good_raw(self, source_id: str) -> dict[str, Any] | None:
        rows = self.known_good_snapshots(source_id, limit=1)
        return rows[0] if rows else None

    def replace_derived(self, source_id: str, rows: list[dict[str, Any]]) -> str:
        table = self.derived_table(source_id)
        self.con.execute(f'DROP TABLE IF EXISTS "{table}"')
        if not rows:
            self.con.execute(f'CREATE TABLE "{table}" (_empty INTEGER)')
            return table
        keys: list[str] = []
        seen: set[str] = set()
        for rec in rows:
            for key in rec:
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        col_types = {key: _infer_col_type([rec.get(key) for rec in rows]) for key in keys}
        cols_sql = ", ".join(f'"{k}" {col_types[k]}' for k in keys)
        self.con.execute(f'CREATE TABLE "{table}" ({cols_sql})')
        placeholders = ", ".join(["?"] * len(keys))
        col_list = ", ".join(f'"{k}"' for k in keys)
        for rec in rows:
            self.con.execute(
                f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})',
                [_sql_value(rec.get(k), col_types[k]) for k in keys],
            )
        return table

    def run_sql(self, sql: str) -> Any:
        return self.con.execute(sql).fetchone()

    def record_run(self, rec: dict[str, Any]) -> None:
        self.con.execute(
            """
            INSERT INTO pipeline_run (
                run_id, source_id, contract_version, started_at, ended_at, status,
                rows_in, rows_out, rows_rejected, schema_errors, stage, span_status,
                http_status, error_type, error_signature, trace_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                rec["run_id"],
                rec["source_id"],
                rec.get("contract_version", 1),
                rec["started_at"],
                rec.get("ended_at"),
                rec["status"],
                rec.get("rows_in", 0),
                rec.get("rows_out", 0),
                rec.get("rows_rejected", 0),
                rec.get("schema_errors", 0),
                rec.get("stage"),
                rec.get("span_status"),
                rec.get("http_status"),
                rec.get("error_type"),
                rec.get("error_signature"),
                rec.get("trace_id"),
            ],
        )

    def record_assertions(self, run_id: str, source_id: str, results: list[dict[str, Any]]) -> None:
        stamp = now()
        for item in results:
            self.con.execute(
                """
                INSERT INTO assertion_result (
                    run_id, source_id, assertion_id, severity, passed, observed, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    source_id,
                    item["id"],
                    item.get("severity", "medium"),
                    bool(item["passed"]),
                    item.get("observed"),
                    stamp,
                ],
            )

    def assertion_results(self, run_id: str) -> dict[str, bool]:
        rows = self.query(
            "SELECT assertion_id, passed FROM assertion_result WHERE run_id = ?",
            [run_id],
        )
        return {r["assertion_id"]: bool(r["passed"]) for r in rows}

    def last_ok_row_count(self, source_id: str) -> int:
        rows = self.query(
            """
            SELECT rows_out FROM pipeline_run
            WHERE source_id = ? AND status IN ('ok', 'healed')
            ORDER BY started_at DESC
            LIMIT 1
            """,
            [source_id],
        )
        return int(rows[0]["rows_out"]) if rows else 0

    def seconds_since_success(self, source_id: str) -> float:
        rows = self.query(
            """
            SELECT ended_at FROM pipeline_run
            WHERE source_id = ? AND status IN ('ok', 'healed') AND ended_at IS NOT NULL
            ORDER BY ended_at DESC
            LIMIT 1
            """,
            [source_id],
        )
        if not rows:
            return 10**9
        ended = rows[0]["ended_at"]
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=now().tzinfo)
        return max(0.0, (now() - ended).total_seconds())

    def recent_failed_runs(self, minutes: int = 15) -> list[dict[str, Any]]:
        cutoff = now() - timedelta(minutes=minutes)
        return self.query(
            """
            SELECT * FROM pipeline_run
            WHERE started_at > ? AND status = 'failed'
            ORDER BY started_at DESC
            """,
            [cutoff],
        )

    def recent_failed_assertions(self, minutes: int = 15) -> list[dict[str, Any]]:
        cutoff = now() - timedelta(minutes=minutes)
        return self.query(
            """
            SELECT source_id, run_id, list(assertion_id) AS failed
            FROM assertion_result
            WHERE evaluated_at > ? AND passed = FALSE
            GROUP BY source_id, run_id
            """,
            [cutoff],
        )

    def write_dead_letter(self, source_id: str, run_id: str, record: dict, reason: str) -> str:
        dlq_id = new_id("dlq")
        self.con.execute(
            """
            INSERT INTO dead_letter (dlq_id, source_id, run_id, record, reason, quarantined_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [dlq_id, source_id, run_id, json.dumps(record), reason, now()],
        )
        return dlq_id

    def upsert_source_state(
        self,
        source_id: str,
        *,
        circuit_state: str | None = None,
        current_rung: int | None = None,
        health: str | None = None,
        contract_patch: dict | None = None,
    ) -> None:
        existing = self.get_source_state(source_id)
        if existing is None:
            self.con.execute(
                """
                INSERT INTO source_state (source_id, circuit_state, current_rung, health, contract_patch, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    source_id,
                    circuit_state or "closed",
                    current_rung if current_rung is not None else 0,
                    health or "healthy",
                    json.dumps(contract_patch) if contract_patch else None,
                    now(),
                ],
            )
            return
        self.con.execute(
            """
            UPDATE source_state SET
                circuit_state = ?,
                current_rung = ?,
                health = ?,
                contract_patch = ?,
                updated_at = ?
            WHERE source_id = ?
            """,
            [
                circuit_state if circuit_state is not None else existing["circuit_state"],
                current_rung if current_rung is not None else existing["current_rung"],
                health if health is not None else existing["health"],
                json.dumps(contract_patch)
                if contract_patch is not None
                else existing["contract_patch"],
                now(),
                source_id,
            ],
        )

    def get_source_state(self, source_id: str) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM source_state WHERE source_id = ?", [source_id])
        return rows[0] if rows else None

    def reset_heal_window(self, source_id: str) -> None:
        """Give the source a fresh hourly budget (demo reset)."""
        cutoff = now() - timedelta(hours=1)
        self.con.execute(
            "DELETE FROM heal_ledger WHERE source_id = ? AND started_at > ?",
            [source_id, cutoff],
        )
        self.con.execute(
            "DELETE FROM incident WHERE source_id = ? AND detected_at > ?",
            [source_id, cutoff],
        )
        self.con.execute(
            "DELETE FROM pending_approval WHERE source_id = ?",
            [source_id],
        )

    def clear_stale_guard(self, source_id: str) -> None:
        """If the latest scrape is healthy, drop leftover Guard / approval state."""
        last = self.query(
            """
            SELECT status FROM pipeline_run
            WHERE source_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            [source_id],
        )
        if not last or last[0]["status"] not in {"ok", "healed"}:
            return
        self.con.execute(
            "DELETE FROM pending_approval WHERE source_id = ? AND status = 'pending'",
            [source_id],
        )
        self.con.execute(
            """
            UPDATE incident
            SET resolution = 'healed', resolved_at = COALESCE(resolved_at, ?)
            WHERE source_id = ? AND resolution = 'open'
            """,
            [now(), source_id],
        )

    def heals_in_last_hour(self, source_id: str) -> int:
        cutoff = now() - timedelta(hours=1)
        row = self.con.execute(
            "SELECT COUNT(*) FROM heal_ledger WHERE source_id = ? AND started_at > ?",
            [source_id, cutoff],
        ).fetchone()
        return int(row[0]) if row else 0

    def fingerprint_count_last_hour(self, fingerprint: str) -> int:
        cutoff = now() - timedelta(hours=1)
        row = self.con.execute(
            "SELECT COUNT(*) FROM incident WHERE fingerprint = ? AND detected_at > ?",
            [fingerprint, cutoff],
        ).fetchone()
        return int(row[0]) if row else 0

    def open_incident(self, rec: dict[str, Any]) -> None:
        self.con.execute(
            """
            INSERT INTO incident (
                incident_id, source_id, fingerprint, failure_class, detected_at,
                resolved_at, mttr_seconds, resolution, attempts, trace_id
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, 'open', 0, ?)
            """,
            [
                rec["incident_id"],
                rec["source_id"],
                rec["fingerprint"],
                rec["failure_class"],
                rec["detected_at"],
                rec.get("trace_id"),
            ],
        )

    def close_incident(self, incident_id: str, resolution: str, mttr_s: float, attempts: int) -> None:
        self.con.execute(
            """
            UPDATE incident
            SET resolved_at = ?, mttr_seconds = ?, resolution = ?, attempts = ?
            WHERE incident_id = ?
            """,
            [now(), mttr_s, resolution, attempts, incident_id],
        )

    def record_heal(self, rec: dict[str, Any]) -> str:
        heal_id = rec.get("heal_id") or new_id("heal")
        self.con.execute(
            """
            INSERT INTO heal_ledger (
                heal_id, incident_id, source_id, fingerprint, failure_class, primitive,
                attempt, autonomy_tier, approved_by, started_at, ended_at,
                verification_passed, before_state, after_state, evidence_trace_id,
                notes, blocked_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                heal_id,
                rec["incident_id"],
                rec["source_id"],
                rec["fingerprint"],
                rec["failure_class"],
                rec["primitive"],
                rec["attempt"],
                rec["autonomy_tier"],
                rec.get("approved_by"),
                rec["started_at"],
                rec.get("ended_at"),
                rec.get("verification_passed"),
                rec.get("before_state"),
                rec.get("after_state"),
                rec.get("evidence_trace_id"),
                rec.get("notes"),
                rec.get("blocked_reason"),
            ],
        )
        return heal_id

    def learn(self, fingerprint: str, failure_class: str, primitive: str, mttr_s: float) -> None:
        existing = self.query("SELECT * FROM heal_pattern WHERE fingerprint = ?", [fingerprint])
        if not existing:
            self.con.execute(
                """
                INSERT INTO heal_pattern (
                    fingerprint, failure_class, successful_primitive, occurrences,
                    avg_mttr_seconds, last_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                """,
                [fingerprint, failure_class, primitive, mttr_s, now()],
            )
            return
        row = existing[0]
        occ = int(row["occurrences"]) + 1
        avg = ((row["avg_mttr_seconds"] or 0) * (occ - 1) + mttr_s) / occ
        self.con.execute(
            """
            UPDATE heal_pattern
            SET successful_primitive = ?, occurrences = ?, avg_mttr_seconds = ?, last_at = ?
            WHERE fingerprint = ?
            """,
            [primitive, occ, avg, now(), fingerprint],
        )

    def learned_primitive(self, fingerprint: str) -> str | None:
        rows = self.query(
            "SELECT successful_primitive FROM heal_pattern WHERE fingerprint = ?",
            [fingerprint],
        )
        return rows[0]["successful_primitive"] if rows else None

    def set_approval(self, incident_id: str, source_id: str, primitive: str, status: str) -> None:
        existing = self.query(
            "SELECT incident_id FROM pending_approval WHERE incident_id = ?", [incident_id]
        )
        if existing:
            self.con.execute(
                "UPDATE pending_approval SET status = ? WHERE incident_id = ?",
                [status, incident_id],
            )
            return
        self.con.execute(
            """
            INSERT INTO pending_approval (incident_id, source_id, primitive, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [incident_id, source_id, primitive, status, now()],
        )

    def approval_status(self, incident_id: str) -> str | None:
        rows = self.query(
            "SELECT status FROM pending_approval WHERE incident_id = ?", [incident_id]
        )
        return rows[0]["status"] if rows else None

    def scoreboard(self) -> dict[str, Any]:
        mttr = self.query(
            """
            SELECT failure_class,
                   COUNT(*) AS heals,
                   ROUND(AVG(DATE_DIFF('second', started_at, ended_at)), 1) AS avg_mttr_s,
                   ROUND(100.0 * AVG(CASE WHEN verification_passed THEN 1.0 ELSE 0.0 END), 1) AS success_pct
            FROM heal_ledger
            WHERE ended_at IS NOT NULL
            GROUP BY failure_class
            """
        )
        autonomy = self.query(
            """
            SELECT ROUND(100.0 * AVG(CASE WHEN approved_by IS NULL THEN 1.0 ELSE 0.0 END), 1) AS autonomy_pct
            FROM heal_ledger
            WHERE verification_passed = TRUE
            """
        )
        incidents = self.query("SELECT resolution, COUNT(*) AS n FROM incident GROUP BY resolution")
        return {
            "by_class": mttr,
            "autonomy_pct": autonomy[0]["autonomy_pct"] if autonomy else None,
            "incidents": incidents,
        }

    def reliability_metrics(self, source_id: str, *, budget: int = 5) -> dict[str, Any]:
        """Judge-facing latency and heal rates for one source."""

        def _s(value: Any) -> float | None:
            if value is None:
                return None
            try:
                out = float(value)
            except (TypeError, ValueError):
                return None
            return round(max(out, 0.0), 3)

        rows = self.query(
            """
            WITH first_heal AS (
                SELECT incident_id, MIN(started_at) AS first_heal_at
                FROM heal_ledger
                WHERE source_id = ?
                GROUP BY incident_id
            ),
            failed_run AS (
                SELECT i.incident_id,
                       (
                           SELECT r.started_at
                           FROM pipeline_run r
                           WHERE r.source_id = i.source_id
                             AND r.status = 'failed'
                             AND r.started_at <= i.detected_at
                           ORDER BY r.started_at DESC
                           LIMIT 1
                       ) AS failed_at
                FROM incident i
                WHERE i.source_id = ?
            )
            SELECT
                i.incident_id,
                i.detected_at,
                i.resolved_at,
                i.mttr_seconds,
                i.resolution,
                i.fingerprint,
                CASE WHEN f.failed_at IS NULL THEN NULL
                     ELSE EPOCH(i.detected_at) - EPOCH(f.failed_at) END AS mttd_s,
                CASE WHEN h.first_heal_at IS NULL THEN NULL
                     ELSE EPOCH(h.first_heal_at) - EPOCH(i.detected_at) END AS mtta_s
            FROM incident i
            LEFT JOIN failed_run f ON f.incident_id = i.incident_id
            LEFT JOIN first_heal h ON h.incident_id = i.incident_id
            WHERE i.source_id = ?
            ORDER BY i.detected_at DESC
            """,
            [source_id, source_id, source_id],
        )
        last = rows[0] if rows else None
        mttd_vals = [_s(r["mttd_s"]) for r in rows if r.get("mttd_s") is not None]
        mtta_vals = [_s(r["mtta_s"]) for r in rows if r.get("mtta_s") is not None]
        mttr_vals = [_s(r["mttr_seconds"]) for r in rows if r.get("mttr_seconds") is not None]
        healed = [r for r in rows if r.get("resolution") == "healed"]
        false_row = self.query(
            """
            SELECT COUNT(*) AS n
            FROM incident a
            WHERE a.source_id = ?
              AND a.resolution = 'healed'
              AND a.resolved_at IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM pipeline_run p
                  WHERE p.source_id = a.source_id
                    AND p.status = 'failed'
                    AND p.started_at > a.resolved_at
                    AND (EPOCH(p.started_at) - EPOCH(a.resolved_at)) < 15
              )
            """,
            [source_id],
        )
        false_heals = int((false_row[0]["n"] or 0) if false_row else 0)

        ended = self.query(
            """
            SELECT
                COUNT(*) AS n,
                SUM(CASE WHEN verification_passed THEN 1 ELSE 0 END) AS passed
            FROM heal_ledger
            WHERE source_id = ? AND ended_at IS NOT NULL
            """,
            [source_id],
        )
        ended_n = int((ended[0]["n"] or 0) if ended else 0)
        passed_n = int((ended[0]["passed"] or 0) if ended else 0)
        finished = [
            r
            for r in rows
            if r.get("resolution") and r.get("resolution") != "open"
        ]
        healed_n = len(healed)
        finished_n = len(finished)
        autonomy = self.query(
            """
            SELECT ROUND(100.0 * AVG(CASE WHEN approved_by IS NULL THEN 1.0 ELSE 0.0 END), 1) AS autonomy_pct
            FROM heal_ledger
            WHERE source_id = ? AND verification_passed = TRUE
            """,
            [source_id],
        )
        used = self.heals_in_last_hour(source_id)
        return {
            "mttd_last_s": _s(last["mttd_s"]) if last else None,
            "mttd_avg_s": _s(sum(mttd_vals) / len(mttd_vals)) if mttd_vals else None,
            "mtta_last_s": _s(last["mtta_s"]) if last else None,
            "mtta_avg_s": _s(sum(mtta_vals) / len(mtta_vals)) if mtta_vals else None,
            "mttr_last_s": _s(last["mttr_seconds"]) if last else None,
            "mttr_avg_s": _s(sum(mttr_vals) / len(mttr_vals)) if mttr_vals else None,
            "heal_success_pct": _s(100.0 * healed_n / finished_n) if finished_n else None,
            "heal_attempts": ended_n,
            "heals_verified": passed_n,
            "incidents_finished": finished_n,
            "false_heal_rate_pct": _s(100.0 * false_heals / len(healed)) if healed else None,
            "false_heals": false_heals,
            "autonomy_pct": autonomy[0]["autonomy_pct"] if autonomy else None,
            "budget_used": used,
            "budget_cap": int(budget),
            "incidents": len(rows),
            "incidents_healed": len(healed),
        }


def _infer_col_type(values: list[Any]) -> str:
    present = [v for v in values if v is not None]
    if not present:
        return "VARCHAR"
    if all(isinstance(v, bool) for v in present):
        return "BOOLEAN"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in present):
        return "INTEGER"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in present):
        return "DOUBLE"
    return "VARCHAR"


def _sql_value(value: Any, col_type: str) -> Any:
    if value is None:
        return None
    if col_type == "INTEGER":
        return int(value)
    if col_type == "DOUBLE":
        return float(value)
    if col_type == "BOOLEAN":
        return bool(value)
    return str(value)
