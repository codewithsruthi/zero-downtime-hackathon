from hydra.primitives.base import HealContext, HealResult, Primitive


class FailoverSource(Primitive):
    id, tier, reversible = "P7", 2, True

    async def applicable(self, ctx: HealContext) -> bool:
        args = ctx.contract["acquisition"]["primary"].get("args") or {}
        return bool(args.get("alternate_url") or ctx.contract.get("_failover_available"))

    async def apply(self, ctx: HealContext) -> HealResult:
        url = ctx.contract["acquisition"]["primary"]["args"]["url"]
        try:
            found = await ctx.pool.invoke(
                "find_alternate_source", query=f"alternative source for {url}"
            )
        except Exception as exc:
            return HealResult(False, self.id, f"search failed: {exc}")
        results = []
        if isinstance(found, dict):
            results = found.get("results") or found.get("organic") or []
        if not results:
            return HealResult(False, self.id, "no alternate URL found")
        alt = results[0]
        alt_url = alt.get("link") or alt.get("url") if isinstance(alt, dict) else str(alt)
        return HealResult(
            True,
            self.id,
            f"failover to {alt_url}",
            contract_patch={"acquisition": {"primary": {"args": {"url": alt_url}}}},
        )
