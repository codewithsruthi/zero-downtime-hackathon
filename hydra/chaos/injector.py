from __future__ import annotations

from typing import Any

from hydra.chaos.faults import FAULTS

ACQUIRE_ONLY = {"http_403", "captcha_wall"}


class ChaosInjector:
    """Runtime flags, never a code edit. Port or CLI can flip these."""

    def __init__(self):
        self._faults: dict[str, dict[str, Any]] = {}

    def inject(self, source_id: str, fault_type: str, **cfg: Any) -> None:
        if fault_type not in FAULTS:
            raise KeyError(f"unknown fault {fault_type!r}. known: {sorted(FAULTS)}")
        self._faults[source_id] = {"type": fault_type, **cfg}

    def clear(self, source_id: str | None = None) -> None:
        if source_id is None:
            self._faults.clear()
            return
        self._faults.pop(source_id, None)

    def active(self, source_id: str) -> dict[str, Any] | None:
        return self._faults.get(source_id)

    def apply(self, source_id: str, payload: str, *, rung: int = 0) -> str:
        spec = self._faults.get(source_id)
        if spec is None:
            return payload
        if spec.get("min_rung", 0) > rung:
            return payload
        acquire_only = spec["type"] in ACQUIRE_ONLY
        if acquire_only and not spec.get("permanent") and rung > spec.get("apply_through_rung", 0):
            return payload
        fn = FAULTS[spec["type"]]
        result = fn(payload, spec)
        if spec.get("once"):
            self._faults.pop(source_id, None)
        return result
