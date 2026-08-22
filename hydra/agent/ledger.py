from __future__ import annotations

import json

from hydra.clock import now
from hydra.ids import new_id


class Ledger:
    def __init__(self, store, pool=None):
        self.store = store
        self.pool = pool

    async def open_incident(self, ctx) -> None:
        self.store.open_incident(
            {
                "incident_id": ctx.incident_id,
                "source_id": ctx.source_id,
                "fingerprint": ctx.fingerprint,
                "failure_class": ctx.failure_class,
                "detected_at": now(),
                "trace_id": ctx.evidence.trace_id,
            }
        )
        self.store.upsert_source_state(ctx.source_id, health="healing")
        await self._port_upsert(
            "hydra_incident",
            ctx.incident_id,
            {
                "failure_class": ctx.failure_class,
                "fingerprint": ctx.fingerprint,
                "detected_at": now().isoformat(),
                "resolution": "open",
            },
        )

    async def close_incident(self, ctx, resolution: str, mttr_s: float) -> None:
        self.store.close_incident(ctx.incident_id, resolution, mttr_s, ctx.attempt)
        health = "healthy" if resolution == "healed" else "failed"
        circuit = "open" if resolution == "escalated" else None
        self.store.upsert_source_state(ctx.source_id, health=health, circuit_state=circuit)

    async def record_attempt(self, ctx, primitive, result, *, verified, delta=None, approved_by=None) -> None:
        self.store.record_heal(
            {
                "heal_id": new_id("heal"),
                "incident_id": ctx.incident_id,
                "source_id": ctx.source_id,
                "fingerprint": ctx.fingerprint,
                "failure_class": ctx.failure_class,
                "primitive": primitive.id,
                "attempt": ctx.attempt,
                "autonomy_tier": primitive.tier,
                "approved_by": approved_by,
                "started_at": now(),
                "ended_at": now(),
                "verification_passed": verified,
                "before_state": json.dumps((delta or {}).get("before")),
                "after_state": json.dumps((delta or {}).get("after")),
                "notes": result.notes,
            }
        )

    async def record_blocked(self, ctx, primitive, reason: str) -> None:
        self.store.record_heal(
            {
                "incident_id": ctx.incident_id,
                "source_id": ctx.source_id,
                "fingerprint": ctx.fingerprint,
                "failure_class": ctx.failure_class,
                "primitive": primitive.id if primitive else "none",
                "attempt": ctx.attempt,
                "autonomy_tier": primitive.tier if primitive else 0,
                "started_at": now(),
                "ended_at": now(),
                "verification_passed": False,
                "notes": reason,
                "blocked_reason": reason,
            }
        )

    async def learn(self, ctx, primitive) -> None:
        self.store.learn(ctx.fingerprint, ctx.failure_class, primitive.id, 0.0)
        await self._port_upsert(
            "hydra_heal_pattern",
            ctx.fingerprint,
            {
                "failure_class": ctx.failure_class,
                "successful_primitive": primitive.id,
            },
        )

    async def _port_upsert(self, blueprint: str, identifier: str, properties: dict) -> None:
        if self.pool is None:
            return
        try:
            await self.pool.invoke(
                "catalog_upsert_entity",
                blueprint=blueprint,
                identifier=identifier,
                properties=properties,
            )
        except Exception:
            return
