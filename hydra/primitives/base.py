from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealContext:
    incident_id: str
    source_id: str
    contract: dict
    failure_class: str
    fingerprint: str
    evidence: Any
    attempt: int
    pool: Any
    store: Any
    runtime: Any
    contracts: Any
    injector: Any
    config: Any
    approver: str | None = None
    proposed_change_summary: str = ""
    blast_radius: str = "derived table for this source only"
    extra: dict = field(default_factory=dict)


@dataclass
class HealResult:
    ok: bool
    primitive: str
    notes: str
    contract_patch: dict | None = None
    requires_reverify: bool = True
    verify_mode: str = "full"


class Primitive(ABC):
    id: str
    tier: int
    reversible: bool

    @abstractmethod
    async def applicable(self, ctx: HealContext) -> bool: ...

    @abstractmethod
    async def apply(self, ctx: HealContext) -> HealResult: ...
