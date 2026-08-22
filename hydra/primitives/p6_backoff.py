import asyncio

from hydra.primitives.base import HealContext, HealResult, Primitive


class BackoffAndReschedule(Primitive):
    id, tier, reversible = "P6", 0, True

    async def applicable(self, ctx: HealContext) -> bool:
        return True

    async def apply(self, ctx: HealContext) -> HealResult:
        delay = ctx.config.backoff_base_s
        if delay:
            await asyncio.sleep(delay)
        return HealResult(True, self.id, f"backed off {delay}s and rescheduled")
