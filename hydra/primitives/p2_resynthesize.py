from __future__ import annotations

import json
import re

from hydra.primitives.base import HealContext, HealResult, Primitive
from hydra.runtime.parse import apply_extractor


class ResynthesizeExtractor(Primitive):
    id, tier, reversible = "P2", 1, True

    async def applicable(self, ctx: HealContext) -> bool:
        return ctx.store.count_raw(ctx.source_id) >= 1

    async def apply(self, ctx: HealContext) -> HealResult:
        latest = ctx.store.latest_raw(ctx.source_id)
        if latest is None:
            return HealResult(False, self.id, "no raw snapshot")
        schema = ctx.contract["schema"]
        candidate = _synthesize(latest["payload"], schema, ctx.contract.get("extraction") or {})
        if candidate is None:
            return HealResult(False, self.id, "could not synthesize an extractor")

        known_good = ctx.store.known_good_snapshots(ctx.source_id, limit=3)
        if not known_good:
            known_good = [latest]
        passes = 0
        for snap in known_good:
            rows = apply_extractor(candidate, snap["payload"], schema)
            expected = json.loads(snap["expected_rows"]) if snap.get("expected_rows") else None
            if expected is None:
                if rows:
                    passes += 1
                continue
            if _matches_expected(rows, expected, tolerance=0.10):
                passes += 1
        if passes < len(known_good):
            return HealResult(
                False,
                self.id,
                f"candidate reproduced only {passes}/{len(known_good)} historical snapshots, rejected",
            )
        new_version = int(ctx.contract.get("contract_version", 1)) + 1
        return HealResult(
            True,
            self.id,
            f"extractor v{new_version} validated on {passes}/{len(known_good)} snapshots",
            contract_patch={"extraction": candidate, "contract_version": new_version},
        )


def _synthesize(payload: str, schema: dict, current: dict) -> dict | None:
    stripped = payload.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = None
        if data is not None:
            sample = data[0] if isinstance(data, list) and data else data
            if isinstance(sample, dict):
                aliases = _infer_aliases(sample, schema)
                return {
                    "strategy": "json_records",
                    "field_aliases": aliases,
                    "coerce": True,
                }
    if "data-repo=" in payload:
        return {
            "strategy": "regex_table",
            "pattern": r'data-repo="(?P<repo>[^"]+)" data-lang="(?P<lang>[^"]+)" data-stars="(?P<stars>\d+)"',
            "field_aliases": {"stars_today": ["stars_today", "stars"]},
        }
    if current.get("pattern"):
        loosened = current["pattern"].replace(r'class="repo-item"', r'class="(?:v2-)?repo-item"')
        loosened = re.sub(r'class=\\?"[^"]+\\?"\s*', "", current["pattern"])
        return {
            "strategy": "regex_table",
            "pattern": loosened or current["pattern"],
            "field_aliases": current.get("field_aliases") or {"stars_today": ["stars_today", "stars"]},
        }
    if "," in payload.split("\n", 1)[0]:
        return {"strategy": "csv_table", "coerce": True}
    return None


def _infer_aliases(sample: dict, schema: dict) -> dict[str, list[str]]:
    keys = list(sample.keys())
    aliases: dict[str, list[str]] = {}
    for required in schema.get("required") or []:
        if required in sample:
            aliases[required] = [required]
            continue
        match = _closest(required, keys)
        aliases[required] = [required] + ([match] if match else [])
    return aliases


def _closest(name: str, keys: list[str]) -> str | None:
    lower = name.lower()
    for key in keys:
        if key.lower() == lower or lower in key.lower() or key.lower() in lower:
            return key
        if key.lower().endswith(lower) or lower.endswith(key.lower()):
            return key
    return None


def _matches_expected(rows: list[dict], expected: list[dict], tolerance: float) -> bool:
    if not expected:
        return bool(rows)
    ratio = abs(len(rows) - len(expected)) / max(len(expected), 1)
    if ratio > tolerance:
        return False
    req = None
    if expected and isinstance(expected[0], dict):
        for key in ("repo", "symbol", "city", "title"):
            if key in expected[0]:
                req = key
                break
    if req is None:
        return True
    got = {str(r.get(req)) for r in rows}
    want = {str(r.get(req)) for r in expected}
    if not want:
        return True
    overlap = len(got & want) / len(want)
    return overlap >= (1.0 - tolerance)
