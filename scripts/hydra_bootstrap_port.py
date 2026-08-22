#!/usr/bin/env python3
"""Upsert HYDRA blueprints into Port. Uses REST when PORT_* keys are set."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hydra.port_setup.blueprints import BLUEPRINTS, SCORECARD
from hydra.port_rest import list_blueprints, port_configured, upsert_blueprint, upsert_scorecard, access_token


def main() -> int:
    print(json.dumps(
        {
            "blueprints": [b["identifier"] for b in BLUEPRINTS],
            "scorecard": SCORECARD["identifier"],
        },
        indent=2,
    ))
    if not port_configured():
        print("Port REST keys missing. Wrote payloads only.")
        return 0
    token = access_token()
    for blueprint in BLUEPRINTS:
        upsert_blueprint(blueprint, token=token)
        print(f"upserted blueprint {blueprint['identifier']}")
    upsert_scorecard(SCORECARD, token=token)
    print(f"upserted scorecard {SCORECARD['identifier']}")
    print("catalog", sorted(list_blueprints(token=token)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
