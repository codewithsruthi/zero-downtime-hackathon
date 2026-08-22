from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GuardDecision:
    allowed: bool
    reason: str
    requires_approval: bool = False
    force_primitive: str | None = None


class Guard:
    def __init__(self, pool, store, config):
        self.pool = pool
        self.store = store
        self.cfg = config

    async def evaluate(self, ctx, primitive) -> GuardDecision:
        state = self.store.get_source_state(ctx.source_id) or {}
        if state.get("circuit_state") == "open":
            return GuardDecision(False, "circuit is open; manual reset required")

        used = self.store.heals_in_last_hour(ctx.source_id)
        budget = ctx.contract["healing"]["heal_budget_per_hour"]
        if used >= budget:
            return GuardDecision(False, f"heal budget exhausted ({used}/{budget} this hour)")

        repeats = self.store.fingerprint_count_last_hour(ctx.fingerprint)
        if repeats >= self.cfg.fingerprint_escalation:
            return GuardDecision(
                True,
                f"fingerprint seen {repeats}x in 1h; structural, escalating",
                force_primitive="P8",
            )

        if ctx.attempt > self.cfg.max_attempts_per_incident:
            return GuardDecision(True, "max attempts reached", force_primitive="P8")

        if primitive.id == "P8":
            return GuardDecision(True, "terminal escalate")

        max_tier = ctx.contract["healing"]["max_autonomy_tier"]
        if primitive.tier > max_tier:
            return GuardDecision(False, f"tier {primitive.tier} exceeds source max {max_tier}")
        if primitive.tier >= 2:
            return GuardDecision(
                True, f"tier {primitive.tier} needs approval", requires_approval=True
            )
        return GuardDecision(True, "within autonomous limits")

    async def request_approval(self, ctx, primitive) -> bool:
        self.store.set_approval(ctx.incident_id, ctx.source_id, primitive.id, "pending")
        if self.cfg.auto_approve_tier2:
            self.store.set_approval(ctx.incident_id, ctx.source_id, primitive.id, "approved")
            ctx.approver = "auto"
            return True
        status = self.store.approval_status(ctx.incident_id)
        if status == "approved":
            ctx.approver = ctx.approver or "operator"
            return True
        return False

    def approve(self, incident_id: str) -> None:
        self.store.set_approval(incident_id, "", "", "approved")
