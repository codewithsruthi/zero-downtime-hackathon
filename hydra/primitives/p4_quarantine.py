from hydra.primitives.base import HealContext, HealResult, Primitive
from hydra.runtime.parse import parse_payload
from hydra.runtime.validate import partition_rows, schema_errors


class QuarantineAndPartialCommit(Primitive):
    id, tier, reversible = "P4", 1, True

    async def applicable(self, ctx: HealContext) -> bool:
        return ctx.store.latest_raw(ctx.source_id) is not None

    async def apply(self, ctx: HealContext) -> HealResult:
        latest = ctx.store.latest_raw(ctx.source_id)
        rows = parse_payload(latest["payload"], ctx.contract)
        errors = schema_errors(rows, ctx.contract["schema"])
        good, bad = partition_rows(rows, errors)
        if not bad:
            return HealResult(False, self.id, "no rows to quarantine")
        for rec in bad:
            ctx.store.write_dead_letter(ctx.source_id, ctx.incident_id, rec, "quarantine")
        ctx.store.replace_derived(ctx.source_id, good)
        return HealResult(
            True,
            self.id,
            f"quarantined {len(bad)} rows, committed {len(good)}",
            contract_patch={"_partial_commit": True},
            verify_mode="assertions_only",
        )
