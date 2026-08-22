from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CLASS_TO_PLAYBOOK = {
    "F1": "F1_acquisition",
    "F2": "F2_structural_drift",
    "F3": "F3_contract_violation",
    "F4": "F4_statistical_anomaly",
    "F5": "F5_freshness",
    "F6": "F6_poison_pill",
}


class Proposer:
    def __init__(self, playbooks_path: Path, store):
        self.store = store
        raw = yaml.safe_load(Path(playbooks_path).read_text())
        self.playbooks = raw["playbooks"]

    async def propose(self, ctx) -> list[dict[str, Any]]:
        name = CLASS_TO_PLAYBOOK[ctx.failure_class]
        plan = list(self.playbooks[name])
        learned = self.store.learned_primitive(ctx.fingerprint)
        if learned:
            rest = [step for step in plan if step["primitive"] != learned]
            plan = [{"primitive": learned, "args": {}}] + rest
        allowed = set(ctx.contract.get("healing", {}).get("allowed_primitives") or [])
        if allowed:
            plan = [step for step in plan if step["primitive"] in allowed]
        return plan
