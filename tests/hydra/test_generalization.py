from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_holdout_source_heals_without_new_code(app):
    app.register(ROOT / "contracts" / "_holdout" / "surprise_source.json")
    healthy = await app.ingest("surprise_source")
    assert healthy.status == "ok"
    assert healthy.rows_out >= 8
    app.break_source("surprise_source", "http_403")
    broken = await app.ingest("surprise_source")
    assert broken.status == "failed"
    resolutions = await app.loop.sweep_and_heal("surprise_source")
    assert resolutions == ["healed"]
    healed = await app.ingest("surprise_source")
    assert healed.status == "ok"
