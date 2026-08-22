from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hydra.factory import HydraApp


def main() -> int:
    app = HydraApp()
    try:
        print(json.dumps(app.store.scoreboard(), indent=2, default=str))
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
