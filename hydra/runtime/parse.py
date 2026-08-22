from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from hydra.errors import ParseError

POISON_MARKERS = ("__POISON__", "\udcff", "\udcfe")


def parse_payload(payload: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    extraction = contract.get("extraction") or {}
    strategy = extraction.get("strategy", "json_records")
    if strategy == "regex_table":
        rows = _parse_regex(payload, extraction.get("pattern", ""))
    elif strategy == "csv_table":
        rows = _parse_csv(payload)
    elif strategy == "json_records":
        rows = _parse_json(payload)
    else:
        raise ParseError(f"unknown extraction strategy {strategy!r}")
    aliases = extraction.get("field_aliases") or {}
    coerce = bool(extraction.get("coerce")) or strategy == "regex_table"
    schema = contract.get("schema") or {}
    out = []
    for row in rows:
        mapped = _apply_aliases(row, aliases)
        if coerce:
            mapped = _coerce_row(mapped, schema)
        mapped["_poisoned"] = _is_poisoned(row) or _is_poisoned(mapped)
        out.append(mapped)
    return out


def apply_extractor(extractor: dict[str, Any], payload: str, schema: dict[str, Any]) -> list[dict[str, Any]]:
    contract = {"extraction": extractor, "schema": schema}
    rows = parse_payload(payload, contract)
    return [{k: v for k, v in row.items() if k != "_poisoned"} for row in rows]


def _parse_regex(payload: str, pattern: str) -> list[dict[str, Any]]:
    if not pattern:
        return []
    compiled = re.compile(pattern)
    rows = []
    for match in compiled.finditer(payload):
        rows.append(dict(match.groupdict()))
    return rows


def _parse_csv(payload: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(payload))
    rows = []
    for rec in reader:
        rows.append({k: _maybe_number(v) if v != "" else None for k, v in rec.items()})
    return rows


def _parse_json(payload: str) -> list[dict[str, Any]]:
    data = json.loads(payload)
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            data = data["data"]
        else:
            data = [data]
    if not isinstance(data, list):
        raise ParseError("JSON payload is not a list of records")
    return [dict(item) for item in data]


def _apply_aliases(row: dict[str, Any], aliases: dict[str, list[str]]) -> dict[str, Any]:
    out = dict(row)
    for dest, sources in aliases.items():
        if out.get(dest) not in (None, ""):
            continue
        for src in sources:
            if src in row and row[src] not in (None, ""):
                out[dest] = row[src]
                break
    return out


def _coerce_row(row: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    props = schema.get("properties") or {}
    out = dict(row)
    for key, spec in props.items():
        if key not in out or out[key] is None:
            continue
        out[key] = _coerce_value(out[key], spec)
    return out


def _coerce_value(value: Any, spec: dict[str, Any]) -> Any:
    types = spec.get("type")
    wanted = types if isinstance(types, list) else [types]
    if "integer" in wanted and isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    if "number" in wanted and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _maybe_number(value: str) -> Any:
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _is_poisoned(row: dict[str, Any]) -> bool:
    if row.get("_invalid_utf8") or row.get("_poison"):
        return True
    for value in row.values():
        if isinstance(value, str) and any(marker in value for marker in POISON_MARKERS):
            return True
    return False
