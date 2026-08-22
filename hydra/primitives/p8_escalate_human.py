from hydra.primitives.base import HealContext, HealResult, Primitive


class OpenCircuitAndEscalate(Primitive):
    id, tier, reversible = "P8", 3, False

    async def applicable(self, ctx: HealContext) -> bool:
        return True

    async def apply(self, ctx: HealContext) -> HealResult:
        ctx.store.upsert_source_state(ctx.source_id, circuit_state="open", health="failed")
        return HealResult(
            True,
            self.id,
            "circuit opened; owner must reset",
            requires_reverify=False,
        )
