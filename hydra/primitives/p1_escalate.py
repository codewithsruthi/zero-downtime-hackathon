from hydra.errors import AcquisitionError
from hydra.primitives.base import HealContext, HealResult, Primitive
from hydra.telemetry import heal_span


class EscalateAcquisition(Primitive):
    id, tier, reversible = "P1", 1, True

    async def applicable(self, ctx: HealContext) -> bool:
        ladder = ctx.contract["acquisition"]["escalation_ladder"]
        return ctx.contract.get("_current_rung", 0) < len(ladder) - 1

    async def apply(self, ctx: HealContext) -> HealResult:
        ladder = ctx.contract["acquisition"]["escalation_ladder"]
        rung = min(ctx.contract.get("_current_rung", 0) + 1, len(ladder) - 1)
        capability = ladder[rung]["capability"]
        with heal_span("act", source_id=ctx.source_id, primitive=self.id, acquisition_rung=rung):
            try:
                acquired = await ctx.runtime.acquirer.acquire(ctx.contract, rung=rung)
            except AcquisitionError as exc:
                return HealResult(False, self.id, f"rung {rung} ({capability}) failed: {exc}")
            if not acquired.payload:
                return HealResult(False, self.id, f"rung {rung} ({capability}) returned nothing")
            ctx.store.write_raw(
                ctx.source_id,
                acquired.payload,
                run_id=ctx.incident_id,
                rung=rung,
                capability=capability,
                url=acquired.url,
                http_status=acquired.http_status,
                media_type=acquired.media_type,
            )
            ctx.store.upsert_source_state(ctx.source_id, current_rung=rung)
            return HealResult(
                True,
                self.id,
                f"escalated to rung {rung} ({capability}), {len(acquired.payload)} bytes",
                contract_patch={"_current_rung": rung},
            )
