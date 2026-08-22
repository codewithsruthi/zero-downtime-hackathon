from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hydra.factory import HydraApp


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_MODE", "replay")
    monkeypatch.setenv("HYDRA_OTEL_DISABLED", "1")
    monkeypatch.setenv("HYDRA_BACKOFF_BASE_S", "0")
    monkeypatch.setenv("HYDRA_ROOT", str(ROOT))
    instance = HydraApp(db_path=tmp_path / "hydra.duckdb")
    yield instance
    instance.close()
