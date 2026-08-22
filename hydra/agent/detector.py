from __future__ import annotations

from hydra.agent.classifier import Evidence


class Detector:
    def __init__(self, pool, store, contracts):
        self.pool = pool
        self.store = store
        self.contracts = contracts

    async def sweep(self, source_id: str | None = None) -> list[Evidence]:
        found: list[Evidence] = []
        found.extend(self._from_failed_runs(source_id))
        found.extend(self._from_assertions(source_id))
        found.extend(self._from_freshness(source_id))
        return self._dedupe(found)

    def _from_failed_runs(self, source_id: str | None) -> list[Evidence]:
        out = []
        for run in self.store.recent_failed_runs():
            if source_id and run["source_id"] != source_id:
                continue
            contract = self.contracts.get(run["source_id"])
            out.append(
                Evidence(
                    source_id=run["source_id"],
                    stage=run.get("stage"),
                    span_status=run.get("span_status"),
                    http_status=run.get("http_status"),
                    error_type=run.get("error_type"),
                    error_message=run.get("error_signature"),
                    rows_parsed=run.get("rows_in"),
                    rows_baseline=self.store.last_ok_row_count(run["source_id"]),
                    schema_errors=run.get("schema_errors") or 0,
                    failed_assertions=self._failed_ids(run["run_id"]),
                    seconds_since_success=self.store.seconds_since_success(run["source_id"]),
                    run_id=run["run_id"],
                    trace_id=run.get("trace_id"),
                )
            )
            _ = contract
        return out

    def _from_assertions(self, source_id: str | None) -> list[Evidence]:
        out = []
        for row in self.store.recent_failed_assertions():
            if source_id and row["source_id"] != source_id:
                continue
            failed = row["failed"]
            if not isinstance(failed, list):
                failed = list(failed) if failed else []
            out.append(
                Evidence(
                    source_id=row["source_id"],
                    stage="validate",
                    span_status="OK",
                    rows_parsed=None,
                    rows_baseline=self.store.last_ok_row_count(row["source_id"]),
                    failed_assertions=[str(x) for x in failed],
                    seconds_since_success=self.store.seconds_since_success(row["source_id"]),
                    run_id=row["run_id"],
                )
            )
        return out

    def _from_freshness(self, source_id: str | None) -> list[Evidence]:
        out = []
        ids = [source_id] if source_id else self.contracts.ids()
        for cid in ids:
            contract = self.contracts.get(cid)
            slo = contract["acquisition"]["freshness_slo_seconds"]
            age = self.store.seconds_since_success(cid)
            if age > slo:
                out.append(
                    Evidence(
                        source_id=cid,
                        stage="acquire",
                        seconds_since_success=age,
                        error_type="Freshness",
                        error_message="no successful run inside SLO",
                    )
                )
        return out

    def _failed_ids(self, run_id: str) -> list[str]:
        results = self.store.assertion_results(run_id)
        return [aid for aid, passed in results.items() if not passed]

    def _dedupe(self, items: list[Evidence]) -> list[Evidence]:
        by_source: dict[str, Evidence] = {}
        for ev in items:
            prev = by_source.get(ev.source_id)
            if prev is None:
                by_source[ev.source_id] = ev
                continue
            if ev.rows_parsed is not None and prev.rows_parsed is None:
                by_source[ev.source_id] = ev
            elif ev.schema_errors > prev.schema_errors:
                by_source[ev.source_id] = ev
        return list(by_source.values())
