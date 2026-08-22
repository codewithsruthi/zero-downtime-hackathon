from __future__ import annotations

from typing import Any


def schema_errors(rows: list[dict[str, Any]], schema: dict[str, Any]) -> list[dict[str, Any]]:
    required = schema.get("required") or []
    props = schema.get("properties") or {}
    errors = []
    for idx, row in enumerate(rows):
        if row.get("_poisoned"):
            errors.append({"index": idx, "reason": "poison_pill", "row": row})
            continue
        for field in required:
            if row.get(field) in (None, ""):
                errors.append({"index": idx, "reason": f"missing:{field}", "row": row})
        for field, spec in props.items():
            if field not in row or row[field] is None:
                continue
            if not _type_ok(row[field], spec.get("type")):
                errors.append({"index": idx, "reason": f"type:{field}", "row": row})
                continue
            if spec.get("minLength") and isinstance(row[field], str):
                if len(row[field]) < spec["minLength"]:
                    errors.append({"index": idx, "reason": f"minLength:{field}", "row": row})
            if spec.get("minimum") is not None and isinstance(row[field], (int, float)):
                if row[field] < spec["minimum"]:
                    errors.append({"index": idx, "reason": f"minimum:{field}", "row": row})
    return errors


def partition_rows(
    rows: list[dict[str, Any]], errors: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bad_idx = {e["index"] for e in errors}
    good = []
    bad = []
    for idx, row in enumerate(rows):
        clean = {k: v for k, v in row.items() if k != "_poisoned"}
        if idx in bad_idx:
            bad.append(clean)
        else:
            good.append(clean)
    return good, bad


def _type_ok(value: Any, declared: Any) -> bool:
    if declared is None:
        return True
    options = declared if isinstance(declared, list) else [declared]
    for item in options:
        if item == "null" and value is None:
            return True
        if item == "string" and isinstance(value, str):
            return True
        if item == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if item == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if item == "boolean" and isinstance(value, bool):
            return True
        if item == "object" and isinstance(value, dict):
            return True
        if item == "array" and isinstance(value, list):
            return True
    return False
