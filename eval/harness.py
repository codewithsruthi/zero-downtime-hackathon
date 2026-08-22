from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hydra.factory import HydraApp


async def run_scenarios(path: Path) -> int:
    scenarios = yaml.safe_load(path.read_text())["scenarios"]
    app = HydraApp()
    failed = 0
    try:
        await app.ingest_all()
        for spec in scenarios:
            if spec.get("holdout"):
                app.register(ROOT / "contracts" / "_holdout" / "surprise_source.json")
                await app.ingest(spec["source"])
            fault = spec["fault"]
            kind = fault["type"]
            args = {k: v for k, v in fault.items() if k != "type"}
            app.break_source(spec["source"], kind, **args)
            broken = await app.ingest(spec["source"])
            if broken.status == "ok":
                print(f"{spec['id']} FAIL fault did not break the run")
                failed += 1
                continue
            if spec["expect"].get("requires_approval"):
                app.config.auto_approve_tier2 = True
            resolutions = await app.loop.sweep_and_heal(spec["source"])
            want_healed = spec["expect"].get("healed", True)
            got = resolutions[-1] if resolutions else "none"
            ok = (got == "healed") == want_healed if want_healed else got == spec["expect"].get("resolution", "escalated")
            if spec["expect"].get("healed") is False:
                ok = got == spec["expect"].get("resolution", "escalated")
            print(f"{spec['id']} {spec['name']}: broken={broken.status} heal={got} {'OK' if ok else 'FAIL'}")
            if not ok:
                failed += 1
            app.injector.clear(spec["source"])
            app.reset_circuit(spec["source"])
            app.config.auto_approve_tier2 = False
    finally:
        app.close()
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=str(ROOT / "eval" / "scenarios.yaml"))
    args = parser.parse_args()
    return asyncio.run(run_scenarios(Path(args.scenarios)))


if __name__ == "__main__":
    raise SystemExit(main())
