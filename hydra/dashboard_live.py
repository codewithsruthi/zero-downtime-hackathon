"""Isolated judge dashboard on live Bright Data.

Does not replace ``make hydra-dashboard`` (replay on :8080).
Never writes ``data/latest.json`` or the replay sidecar ``data/hydra-live.json``.
"""

from __future__ import annotations

import os
from pathlib import Path

from hydra.config import _repo_root, load_dotenv
from hydra.live_snapshot import AMAZON

LIVE_DB_NAME = "hydra-live.duckdb"
JUDGE_LIVE_NAME = "hydra-judge.json"
JUDGE_FAULTS_NAME = "hydra-judge-faults.json"
LIVE_PORT = 8081
LIVE_INTERVAL_S = "60"
LIVE_LABEL = "live Bright Data · judge"


def _abs(root: Path, value: str | None, default: Path) -> str:
    if not (value or "").strip():
        return str(default.resolve())
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        path = root / path
    return str(path.resolve())


def isolate(root: Path | None = None) -> dict[str, str]:
    """Force live mode and sidecar files that the replay dashboard does not use."""
    load_dotenv()
    base = Path(root).resolve() if root else _repo_root()
    db = _abs(
        base,
        os.environ.get("HYDRA_LIVE_DB_PATH"),
        base / LIVE_DB_NAME,
    )
    snap = _abs(
        base,
        os.environ.get("HYDRA_JUDGE_LIVE_PATH"),
        base / "data" / JUDGE_LIVE_NAME,
    )
    faults = _abs(
        base,
        os.environ.get("HYDRA_JUDGE_FAULTS_PATH"),
        base / "data" / JUDGE_FAULTS_NAME,
    )
    os.environ["HYDRA_MODE"] = "live"
    os.environ["HYDRA_DB_PATH"] = db
    os.environ["HYDRA_LIVE_PATH"] = snap
    os.environ["HYDRA_FAULTS_PATH"] = faults
    os.environ["HYDRA_DASHBOARD_PORT"] = (
        os.environ.get("HYDRA_DASHBOARD_LIVE_PORT") or str(LIVE_PORT)
    ).strip()
    os.environ["HYDRA_DASHBOARD_INTERVAL_S"] = (
        os.environ.get("HYDRA_DASHBOARD_LIVE_INTERVAL_S") or LIVE_INTERVAL_S
    ).strip()
    os.environ.setdefault("HYDRA_DASHBOARD_CONTROLS", "1")
    os.environ.setdefault("HYDRA_DASHBOARD_HOLD_S", "3.5")
    if not (os.environ.get("HYDRA_DASHBOARD_LABEL") or "").strip():
        os.environ["HYDRA_DASHBOARD_LABEL"] = LIVE_LABEL
    return {
        "db": db,
        "live": snap,
        "faults": faults,
        "port": os.environ["HYDRA_DASHBOARD_PORT"],
    }


def serve_forever(
    *,
    watch: bool = False,
    host: str | None = None,
    port: int | None = None,
    source: str = AMAZON,
) -> int:
    paths = isolate()
    from hydra.dashboard import serve_forever as serve_replay_twin
    from hydra.factory import HydraApp
    from hydra.runtime.datasets import api_token

    if not api_token():
        print(
            "warning: BRIGHTDATA_API_TOKEN (or BRIGHTDATA_API_KEY) is empty; "
            "live ingest will fail until it is set",
            flush=True,
        )
    print("HYDRA judge dashboard: live Bright Data, isolated from replay :8080", flush=True)
    print(f"  duckdb   {paths['db']}", flush=True)
    print(f"  snapshot {paths['live']}", flush=True)
    print(f"  faults   {paths['faults']}", flush=True)
    app = HydraApp()
    bind = port if port is not None else int(paths["port"])
    try:
        return serve_replay_twin(
            watch=watch,
            host=host,
            port=bind,
            source=source,
            app=app,
            live_path=app.live_path,
            faults_path=app.faults_path,
        )
    finally:
        app.close()
