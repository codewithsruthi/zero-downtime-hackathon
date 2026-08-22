from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from hydra.clock import now
from hydra.errors import AcquisitionError
from hydra.ids import new_id
from hydra.runtime.acquire import Acquirer
from hydra.runtime.parse import parse_payload
from hydra.runtime.validate import partition_rows, schema_errors
from hydra.store import Store
from hydra.telemetry import current_trace_id, stage_span

_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


@dataclass
class RunResult:
    run_id: str
    source_id: str
    status: str
    rows_in: int = 0
    rows_out: int = 0
    rows_rejected: int = 0
    schema_errors: int = 0
    failed_assertions: list[str] = field(default_factory=list)
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    stage: str | None = None
    span_status: str | None = None
    http_status: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    snapshot_id: str | None = None
    trace_id: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)


class Pipeline:
    def __init__(self, store: Store, acquirer: Acquirer, contracts):
        self.store = store
        self.acquirer = acquirer
        self.contracts = contracts

    async def execute(
        self,
        contract: dict[str, Any],
        *,
        reason: str = "ingest",
        skip_acquire: bool = False,
        snapshot: dict[str, Any] | None = None,
        assertions_only: bool = False,
    ) -> RunResult:
        source_id = contract["contract_id"]
        run_id = new_id("run")
        started = now()
        result = RunResult(run_id=run_id, source_id=source_id, status="ok")
        with stage_span(
            "hydra.ingest",
            source_id,
            run_id,
            contract_version=contract.get("contract_version", 1),
        ) as root:
            try:
                if assertions_only:
                    await self._assert_existing(contract, result)
                elif skip_acquire:
                    await self._from_snapshot(contract, result, snapshot)
                else:
                    await self._full(contract, result)
            except AcquisitionError as exc:
                result.status = "failed"
                result.stage = "acquire"
                result.span_status = "ERROR"
                result.http_status = exc.http_status
                result.error_type = exc.error_type
                result.error_message = str(exc)
            except Exception as exc:
                result.status = "failed"
                result.stage = result.stage or "load"
                result.span_status = "ERROR"
                result.error_type = type(exc).__name__
                result.error_message = str(exc)
            if result.status == "ok" and result.failed_assertions:
                result.status = "failed"
                result.stage = result.stage or "validate"
            if result.status == "ok" and result.schema_errors:
                result.status = "failed"
                result.stage = result.stage or "validate"
                result.error_type = result.error_type or "SchemaError"
                result.error_message = result.error_message or f"{result.schema_errors} schema errors"
            result.trace_id = current_trace_id()
            root.set_attribute("hydra.rows_in", result.rows_in)
            root.set_attribute("hydra.rows_out", result.rows_out)
            if result.status != "ok":
                try:
                    from opentelemetry.trace import Status, StatusCode

                    root.set_status(Status(StatusCode.ERROR, result.error_type or result.status))
                except Exception:
                    pass
                if result.error_type:
                    root.set_attribute(
                        "hydra.error_signature",
                        f"{result.error_type}:{(result.error_message or '')[:200]}",
                    )
        ended = now()
        self.store.record_run(
            {
                "run_id": run_id,
                "source_id": source_id,
                "contract_version": contract.get("contract_version", 1),
                "started_at": started,
                "ended_at": ended,
                "status": result.status,
                "rows_in": result.rows_in,
                "rows_out": result.rows_out,
                "rows_rejected": result.rows_rejected,
                "schema_errors": result.schema_errors,
                "stage": result.stage,
                "span_status": result.span_status or ("OK" if result.status == "ok" else "ERROR"),
                "http_status": result.http_status,
                "error_type": result.error_type,
                "error_signature": (
                    f"{result.error_type}:{result.error_message[:200]}"
                    if result.error_type
                    else None
                ),
                "trace_id": result.trace_id,
            }
        )
        if result.assertion_results:
            self.store.record_assertions(run_id, source_id, result.assertion_results)
        health = "healthy" if result.status == "ok" else "degraded"
        state = self.store.get_source_state(source_id) or {}
        self.store.upsert_source_state(source_id, health=health, current_rung=contract.get("_current_rung", state.get("current_rung", 0)))
        _ = reason
        return result

    async def _full(self, contract: dict[str, Any], result: RunResult) -> None:
        source_id = contract["contract_id"]
        with stage_span("acquire", source_id, result.run_id):
            acquired = await self.acquirer.acquire(contract)
        result.http_status = acquired.http_status
        result.stage = "acquire"
        result.snapshot_id = self.store.write_raw(
            source_id,
            acquired.payload,
            run_id=result.run_id,
            rung=acquired.rung,
            capability=acquired.capability,
            url=acquired.url,
            http_status=acquired.http_status,
            media_type=acquired.media_type,
        )
        await self._parse_load_assert(contract, result, acquired.payload, snapshot_id=result.snapshot_id)

    async def _from_snapshot(self, contract: dict[str, Any], result: RunResult, snapshot: dict[str, Any] | None) -> None:
        source_id = contract["contract_id"]
        with stage_span("acquire", source_id, result.run_id, replay=True):
            snap = snapshot or self.store.latest_good_raw(source_id) or self.store.latest_raw(source_id)
            if snap is None:
                raise RuntimeError(f"no raw snapshot for {source_id}")
        result.snapshot_id = snap["snapshot_id"]
        result.http_status = snap.get("http_status") or 200
        await self._parse_load_assert(contract, result, snap["payload"], snapshot_id=snap["snapshot_id"])

    async def _assert_existing(self, contract: dict[str, Any], result: RunResult) -> None:
        table = self.store.derived_table(contract["contract_id"])
        result.assertion_results = self._run_assertions(contract, table)
        result.failed_assertions = [a["id"] for a in result.assertion_results if not a["passed"]]
        result.stage = "validate"

    async def _parse_load_assert(
        self, contract: dict[str, Any], result: RunResult, payload: str, *, snapshot_id: str
    ) -> None:
        source_id = contract["contract_id"]
        with stage_span("parse", source_id, result.run_id):
            parsed = parse_payload(payload, contract)
        result.rows_in = len(parsed)
        result.stage = "parse"
        with stage_span("validate", source_id, result.run_id, rows_in=len(parsed)):
            errors = schema_errors(parsed, contract["schema"])
        result.schema_errors = len(errors)
        good, bad = partition_rows(parsed, errors)
        partial = bool(contract.get("_partial_commit"))
        if bad and not partial:
            if any(e["reason"] == "poison_pill" for e in errors):
                result.stage = "load"
                result.span_status = "ERROR"
                result.error_type = "ConversionError"
                result.error_message = f"{len(bad)} poison rows"
                result.status = "failed"
                result.rows_rejected = len(bad)
                return
        for rec in bad:
            self.store.write_dead_letter(source_id, result.run_id, rec, "schema_or_poison")
        result.rows_rejected = len(bad)
        result.rows = good
        with stage_span("load", source_id, result.run_id, rows_out=len(good)):
            self.store.replace_derived(source_id, good)
        result.rows_out = len(good)
        if result.status != "failed" and snapshot_id and good:
            self.store.mark_raw_expected(snapshot_id, good)
        table = self.store.derived_table(source_id)
        with stage_span("derive", source_id, result.run_id):
            result.assertion_results = self._run_assertions(contract, table)
        result.failed_assertions = [a["id"] for a in result.assertion_results if not a["passed"]]
        result.stage = "validate" if result.failed_assertions else "derive"

    def _run_assertions(self, contract: dict[str, Any], table: str) -> list[dict[str, Any]]:
        prev = self.store.last_ok_row_count(contract["contract_id"])
        out = []
        for assertion in contract["assertions"]:
            sql = assertion["sql"]
            if not _SELECT_ONLY.match(sql):
                out.append(
                    {
                        "id": assertion["id"],
                        "severity": assertion.get("severity", "medium"),
                        "passed": False,
                        "observed": "rejected: not a SELECT",
                    }
                )
                continue
            rendered = (
                sql.replace("{{table}}", f'"{table}"')
                .replace("{{prev_count}}", str(prev))
            )
            try:
                row = self.store.run_sql(rendered)
                passed = bool(row[0]) if row else False
                observed = str(row[0]) if row else "empty"
            except Exception as exc:
                passed = False
                observed = str(exc)
            out.append(
                {
                    "id": assertion["id"],
                    "severity": assertion.get("severity", "medium"),
                    "passed": passed,
                    "observed": observed,
                }
            )
        return out
