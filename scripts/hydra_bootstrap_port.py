#!/usr/bin/env python3
"""Upsert HYDRA blueprints. Live mode needs a working Port MCP session."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hydra.port_setup.blueprints import BLUEPRINTS, SCORECARD


async def main() -> int:
    print(json.dumps({"blueprints": [b["identifier"] for b in BLUEPRINTS], "scorecard": SCORECARD["identifier"]}, indent=2))
    print("Replay/print only. In a Cursor session, call Port upsert_blueprint / upsert_scorecard with these payloads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
