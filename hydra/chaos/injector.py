from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hydra.chaos.faults import FAULTS

ACQUIRE_ONLY = {"http_403", "captcha_wall"}


class ChaosInjector:
    """Runtime flags, never a code edit. Port or CLI can flip these.

    When ``persist_path`` is set, inject/clear survive across processes so a
    dashboard watch loop can see ``python -m hydra break``.
    """

    def __init__(self, persist_path: str | Path | None = None):
        self._faults: dict[str, dict[str, Any]] = {}
        self.persist_path = Path(persist_path) if persist_path else None
        if self.persist_path:
            self.load()

    def inject(self, source_id: str, fault_type: str, **cfg: Any) -> None:
        if fault_type not in FAULTS:
            raise KeyError(f"unknown fault {fault_type!r}. known: {sorted(FAULTS)}")
        payload = {"type": fault_type, **cfg}
        self._faults[source_id] = payload
        self._save()

    def clear(self, source_id: str | None = None) -> None:
        if source_id is None:
            self._faults.clear()
        else:
            self._faults.pop(source_id, None)
        self._save()

    def active(self, source_id: str) -> dict[str, Any] | None:
        return self._faults.get(source_id)

    def all_faults(self) -> dict[str, dict[str, Any]]:
        return {key: dict(val) for key, val in self._faults.items()}

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
        try:
            return fn(payload, spec)
        finally:
            if spec.get("once"):
                self._faults.pop(source_id, None)
                self._save()

    def load(self) -> None:
        path = self.persist_path
        if path is None or not path.is_file():
            return
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        loaded: dict[str, dict[str, Any]] = {}
        for source_id, spec in raw.items():
            if not isinstance(spec, dict):
                continue
            fault_type = spec.get("type")
            if fault_type not in FAULTS:
                continue
            loaded[str(source_id)] = dict(spec)
        self._faults = loaded

    def _save(self) -> None:
        path = self.persist_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._faults, indent=2, default=str) + "\n")
            tmp.replace(path)
        except OSError:
            return
