from __future__ import annotations

from hydra.telemetry import heal_span


class Verifier:
    def __init__(self, store, runtime):
        self.store = store
        self.runtime = runtime

    async def verify(self, ctx, *, mode: str = "full") -> tuple[bool, dict]:
        with heal_span("verify", source_id=ctx.source_id, fingerprint=ctx.fingerprint):
            failing = list(ctx.evidence.failed_assertions)
            if not failing:
                failing = [a["id"] for a in ctx.contract["assertions"]]

            if mode == "replay":
                run = await self.runtime.execute(
                    ctx.contract, reason="verification", skip_acquire=True
                )
            elif mode == "assertions_only":
                run = await self.runtime.execute(
                    ctx.contract, reason="verification", assertions_only=True
                )
            else:
                run = await self.runtime.execute(ctx.contract, reason="verification")

            results = {item["id"]: item["passed"] for item in run.assertion_results}
            after = {aid: bool(results.get(aid, False)) for aid in failing}
            passed = bool(after) and all(after.values()) and run.status in {"ok", "healed"}
            if run.status != "ok" and not after:
                passed = False
            return passed, {
                "before": {aid: False for aid in failing},
                "after": after,
                "verification_run_id": run.run_id,
                "run_status": run.status,
            }
