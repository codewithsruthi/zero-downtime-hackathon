from hydra.primitives.base import HealContext, HealResult, Primitive
from hydra.runtime.parse import parse_payload
from hydra.runtime.validate import schema_errors


class RelaxOrEvolveSchema(Primitive):
    id, tier, reversible = "P3", 2, True

    async def applicable(self, ctx: HealContext) -> bool:
        return ctx.store.latest_raw(ctx.source_id) is not None

    async def apply(self, ctx: HealContext) -> HealResult:
        latest = ctx.store.latest_raw(ctx.source_id)
        payload = latest["payload"]
        schema = ctx.contract["schema"]
        extraction = dict(ctx.contract.get("extraction") or {})
        aliases = dict(extraction.get("field_aliases") or {})
        try:
            import json

            data = json.loads(payload)
            sample = data[0] if isinstance(data, list) and data else data
        except Exception:
            sample = None
        if isinstance(sample, dict):
            for required in schema.get("required") or []:
                if required in sample:
                    continue
                for key in sample:
                    if required in key or key in required:
                        aliases[required] = [required, key]
            extraction["field_aliases"] = aliases
            extraction["coerce"] = True
        patched = {
            "extraction": extraction,
            "schema": {**schema, "additionalProperties": True},
            "contract_version": int(ctx.contract.get("contract_version", 1)) + 1,
        }
        trial = {**ctx.contract, **patched}
        rows = parse_payload(payload, trial)
        errors = schema_errors(rows, trial["schema"])
        if errors and not aliases:
            return HealResult(False, self.id, f"schema still rejects {len(errors)} rows")
        return HealResult(
            True,
            self.id,
            f"evolved schema aliases={aliases} coerce=true",
            contract_patch=patched,
        )
