from __future__ import annotations

from hydra.store import Store


class Diagnoser:
    def __init__(self, store: Store):
        self.store = store

    def diagnose(self, ctx) -> dict:
        latest = self.store.latest_raw(ctx.source_id)
        good = self.store.latest_good_raw(ctx.source_id)
        latest_payload = (latest or {}).get("payload") or ""
        good_payload = (good or {}).get("payload") or ""
        changed = "payloads look structurally identical"
        if latest_payload and good_payload and latest_payload != good_payload:
            changed = "raw payload differs from last known good snapshot"
        elif ctx.evidence.http_status and ctx.evidence.http_status >= 400:
            changed = f"acquire returned HTTP {ctx.evidence.http_status}"
        elif ctx.evidence.schema_errors:
            changed = f"{ctx.evidence.schema_errors} rows failed the contract schema"
        elif ctx.evidence.rows_parsed == 0:
            changed = "extraction returned zero rows"
        return {
            "what_changed": changed,
            "confidence": 0.7 if latest_payload != good_payload else 0.3,
            "recommended_primitive": None,
        }
