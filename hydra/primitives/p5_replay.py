from hydra.primitives.base import HealContext, HealResult, Primitive


class ReplayFromRaw(Primitive):
    id, tier, reversible = "P5", 0, True

    async def applicable(self, ctx: HealContext) -> bool:
        return ctx.store.latest_good_raw(ctx.source_id) is not None

    async def apply(self, ctx: HealContext) -> HealResult:
        snap = ctx.store.latest_good_raw(ctx.source_id)
        run = await ctx.runtime.execute(
            ctx.contract, reason="p5_replay", skip_acquire=True, snapshot=snap
        )
        if run.status != "ok":
            return HealResult(False, self.id, f"replay failed: {run.error_message}")
        return HealResult(
            True,
            self.id,
            f"rebuilt derived from snapshot {snap['snapshot_id']}",
            verify_mode="full",
        )
