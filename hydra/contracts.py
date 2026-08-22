from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from hydra.errors import ContractError
from hydra.ids import require_slug

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


class ContractRegistry:
    def __init__(self, contracts_dir: Path, meta_schema: dict[str, Any] | None = None):
        self.contracts_dir = Path(contracts_dir)
        self.meta_schema = meta_schema
        self._contracts: dict[str, dict[str, Any]] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}

    def load_seed(self) -> None:
        if not self.contracts_dir.exists():
            raise ContractError(f"contracts dir missing: {self.contracts_dir}")
        for path in sorted(self.contracts_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            self.add(load_contract(path, meta_schema=self.meta_schema))

    def add(self, contract: dict[str, Any]) -> dict[str, Any]:
        cid = require_slug(contract["contract_id"], what="contract_id")
        self._contracts[cid] = copy.deepcopy(contract)
        self._history.setdefault(cid, []).append(copy.deepcopy(contract))
        return self._contracts[cid]

    def get(self, contract_id: str) -> dict[str, Any]:
        try:
            return self._contracts[contract_id]
        except KeyError as exc:
            raise ContractError(f"unknown contract {contract_id!r}") from exc

    def ids(self) -> list[str]:
        return sorted(self._contracts)

    def patch(self, contract_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.get(contract_id)
        self._history.setdefault(contract_id, []).append(copy.deepcopy(current))
        merged = _deep_merge(current, patch)
        self._contracts[contract_id] = merged
        return merged

    def rollback(self, contract_id: str) -> dict[str, Any]:
        hist = self._history.get(contract_id) or []
        if not hist:
            return self.get(contract_id)
        previous = copy.deepcopy(hist.pop())
        self._contracts[contract_id] = previous
        return previous

    def register_path(self, path: str | Path) -> dict[str, Any]:
        return self.add(load_contract(path, meta_schema=self.meta_schema))


def load_contract(path: str | Path, meta_schema: dict[str, Any] | None = None) -> dict[str, Any]:
    path = Path(path)
    try:
        contract = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc
    validate_contract(contract, meta_schema=meta_schema)
    return contract


def load_meta_schema(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def validate_contract(contract: dict[str, Any], meta_schema: dict[str, Any] | None = None) -> None:
    if not isinstance(contract, dict):
        raise ContractError("contract must be an object")
    require_slug(str(contract.get("contract_id", "")), what="contract_id")
    if "acquisition" not in contract or "schema" not in contract or "assertions" not in contract:
        raise ContractError("contract needs acquisition, schema, and assertions")
    if not contract["assertions"]:
        raise ContractError("contract needs at least one assertion")
    if meta_schema is not None and jsonschema is not None:
        try:
            jsonschema.validate(contract, meta_schema)
        except jsonschema.ValidationError as exc:
            raise ContractError(f"contract failed meta-schema: {exc.message}") from exc


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out
