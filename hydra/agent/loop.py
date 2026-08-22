from __future__ import annotations

import asyncio
import time

from hydra.agent.classifier import classify, fingerprint
from hydra.ids import new_id
from hydra.primitives.base import HealContext
from hydra.telemetry import heal_span


class HealingLoop:
    def __init__(
        self,
        pool,
        store,
        contracts,
        detector,
        proposer,
        guard,
        executor,
        verifier,
        ledger,
        runtime,
        injector,
        config,
    ):
        self.pool = pool
        self.store = store
        self.contracts = contracts
        self.detector = detector
        self.proposer = proposer
        self.guard = guard
        self.executor = executor
        self.verifier = verifier
        self.ledger = ledger
        self.runtime = runtime
        self.injector = injector
        self.config = config
        self._inflight: set[str] = set()

    async def run_forever(self, interval_s: int | None = None):
        delay = interval_s if interval_s is not None else self.config.detect_interval_s
        while True:
            try:
                await self.sweep_and_heal()
            except Exception as exc:
                print(f"[loop] sweep failed: {exc}")
            await asyncio.sleep(delay)

    async def sweep_and_heal(self, source_id: str | None = None) -> list[str]:
        resolutions = []
        for evidence in await self.detector.sweep(source_id):
            if evidence.source_id in self._inflight:
                continue
            resolutions.append(await self.heal(evidence))
        return resolutions

    async def heal(self, evidence) -> str:
        t0 = time.time()
        contract = self.contracts.get(evidence.source_id)
        incident_id = new_id("inc")
        with heal_span("classify", source_id=evidence.source_id):
            fclass = classify(evidence, contract["acquisition"]["freshness_slo_seconds"])
            fp = fingerprint(fclass, evidence)

        ctx = HealContext(
            incident_id=incident_id,
            source_id=evidence.source_id,
            contract=contract,
            failure_class=fclass,
            fingerprint=fp,
            evidence=evidence,
            attempt=0,
            pool=self.pool,
            store=self.store,
            runtime=self.runtime,
            contracts=self.contracts,
            injector=self.injector,
            config=self.config,
        )
        self._inflight.add(evidence.source_id)
        try:
            await self.ledger.open_incident(ctx)
            plan = await self.proposer.propose(ctx)
            for attempt, step in enumerate(plan, start=1):
                ctx.attempt = attempt
                primitive = self.executor.get(step["primitive"])
                decision = await self.guard.evaluate(ctx, primitive)
                if decision.force_primitive:
                    primitive = self.executor.get(decision.force_primitive)
                elif not decision.allowed:
                    await self.ledger.record_blocked(ctx, primitive, decision.reason)
                    break

                if primitive.id != "P8" and not await primitive.applicable(ctx):
                    continue

                approved_by = None
                if decision.requires_approval:
                    if not await self.guard.request_approval(ctx, primitive):
                        await self.ledger.record_blocked(
                            ctx, primitive, "approval denied or timed out"
                        )
                        await self.ledger.close_incident(
                            ctx, resolution="blocked", mttr_s=time.time() - t0
                        )
                        return "blocked"
                    approved_by = ctx.approver

                result = await primitive.apply(ctx)
                if primitive.id == "P8":
                    await self.ledger.record_attempt(
                        ctx, primitive, result, verified=False, approved_by=approved_by
                    )
                    await self.ledger.close_incident(
                        ctx, resolution="escalated", mttr_s=time.time() - t0
                    )
                    return "escalated"

                if not result.ok:
                    await self.ledger.record_attempt(ctx, primitive, result, verified=False)
                    continue

                if result.contract_patch:
                    self.contracts.patch(evidence.source_id, result.contract_patch)
                    ctx.contract = self.contracts.get(evidence.source_id)

                if not result.requires_reverify:
                    await self.ledger.record_attempt(
                        ctx, primitive, result, verified=True, approved_by=approved_by
                    )
                    await self.ledger.close_incident(
                        ctx, resolution="healed", mttr_s=time.time() - t0
                    )
                    await self.ledger.learn(ctx, primitive)
                    return "healed"

                verified, delta = await self.verifier.verify(ctx, mode=result.verify_mode)
                await self.ledger.record_attempt(
                    ctx,
                    primitive,
                    result,
                    verified=verified,
                    delta=delta,
                    approved_by=approved_by,
                )
                if verified:
                    await self.ledger.close_incident(
                        ctx, resolution="healed", mttr_s=time.time() - t0
                    )
                    await self.ledger.learn(ctx, primitive)
                    return "healed"
                if primitive.reversible and result.contract_patch:
                    self.contracts.rollback(evidence.source_id)
                    ctx.contract = self.contracts.get(evidence.source_id)

            await self.ledger.close_incident(ctx, resolution="escalated", mttr_s=time.time() - t0)
            return "escalated"
        finally:
            self._inflight.discard(evidence.source_id)
