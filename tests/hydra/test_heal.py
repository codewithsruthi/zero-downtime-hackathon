import pytest


@pytest.mark.asyncio
async def test_http_403_heals_via_p1(app):
    await app.ingest("gh_trending_repos")
    app.break_source("gh_trending_repos", "http_403")
    broken = await app.ingest("gh_trending_repos")
    assert broken.status == "failed"
    assert broken.http_status == 403
    resolutions = await app.loop.sweep_and_heal("gh_trending_repos")
    assert resolutions == ["healed"]
    heals = app.store.query(
        "SELECT primitive, verification_passed FROM heal_ledger WHERE source_id = ? ORDER BY started_at",
        ["gh_trending_repos"],
    )
    assert any(row["primitive"] == "P1" and row["verification_passed"] for row in heals)


@pytest.mark.asyncio
async def test_selector_drift_heals_via_p2(app):
    await app.ingest("gh_trending_repos")
    await app.ingest("gh_trending_repos")
    await app.ingest("gh_trending_repos")
    app.break_source("gh_trending_repos", "selector_drift")
    broken = await app.ingest("gh_trending_repos")
    assert broken.status == "failed"
    assert broken.rows_in == 0
    resolutions = await app.loop.sweep_and_heal("gh_trending_repos")
    assert resolutions == ["healed"]
    heals = app.store.query(
        "SELECT primitive FROM heal_ledger WHERE source_id = ? AND verification_passed = TRUE",
        ["gh_trending_repos"],
    )
    assert "P2" in [row["primitive"] for row in heals]


@pytest.mark.asyncio
async def test_field_rename_requires_approval(app):
    await app.ingest("crypto_prices_api")
    app.break_source("crypto_prices_api", "field_rename", **{"from": "price", "to": "current_price"})
    broken = await app.ingest("crypto_prices_api")
    assert broken.status == "failed"
    assert broken.schema_errors > 0
    resolutions = await app.loop.sweep_and_heal("crypto_prices_api")
    assert resolutions == ["blocked"]
    pending = app.store.query("SELECT status FROM pending_approval")
    assert pending and pending[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_field_rename_heals_after_approval(app):
    await app.ingest("crypto_prices_api")
    app.config.auto_approve_tier2 = True
    app.break_source("crypto_prices_api", "field_rename", **{"from": "price", "to": "current_price"})
    await app.ingest("crypto_prices_api")
    resolutions = await app.loop.sweep_and_heal("crypto_prices_api")
    assert resolutions == ["healed"]
    heals = app.store.query(
        "SELECT primitive, approved_by FROM heal_ledger WHERE verification_passed = TRUE"
    )
    assert any(row["primitive"] == "P3" and row["approved_by"] for row in heals)


@pytest.mark.asyncio
async def test_poison_quarantines(app):
    await app.ingest("city_open_data")
    app.break_source("city_open_data", "poison_record", at=4)
    broken = await app.ingest("city_open_data")
    assert broken.status == "failed"
    assert broken.error_type == "ConversionError"
    resolutions = await app.loop.sweep_and_heal("city_open_data")
    assert resolutions == ["healed"]
    dlq = app.store.query("SELECT * FROM dead_letter WHERE source_id = ?", ["city_open_data"])
    assert dlq
    heals = app.store.query(
        "SELECT primitive FROM heal_ledger WHERE verification_passed = TRUE"
    )
    assert "P4" in [row["primitive"] for row in heals]


@pytest.mark.asyncio
async def test_null_flood_replays_from_raw(app):
    await app.ingest("city_open_data")
    app.break_source("city_open_data", "null_flood", field="population", rate=0.8, once=True)
    broken = await app.ingest("city_open_data")
    assert broken.status == "failed"
    resolutions = await app.loop.sweep_and_heal("city_open_data")
    assert resolutions == ["healed"]


@pytest.mark.asyncio
async def test_permanent_403_escalates(app):
    await app.ingest("gh_trending_repos")
    app.break_source("gh_trending_repos", "http_403", permanent=True)
    await app.ingest("gh_trending_repos")
    resolutions = await app.loop.sweep_and_heal("gh_trending_repos")
    assert resolutions == ["escalated"]
    state = app.store.get_source_state("gh_trending_repos")
    assert state["circuit_state"] == "open"


@pytest.mark.asyncio
async def test_fingerprint_escalation_opens_circuit(app):
    await app.ingest("gh_trending_repos")
    app.config.fingerprint_escalation = 2
    app.break_source("gh_trending_repos", "http_403", permanent=True)
    await app.ingest("gh_trending_repos")
    first = await app.loop.sweep_and_heal("gh_trending_repos")
    assert first == ["escalated"]
    app.reset_circuit("gh_trending_repos")
    await app.ingest("gh_trending_repos")
    second = await app.loop.sweep_and_heal("gh_trending_repos")
    assert second == ["escalated"]
    heals = app.store.query("SELECT primitive FROM heal_ledger ORDER BY started_at")
    assert heals[-1]["primitive"] == "P8"


@pytest.mark.asyncio
async def test_verifier_uses_same_assertion(app):
    await app.ingest("gh_trending_repos")
    app.break_source("gh_trending_repos", "selector_drift")
    broken = await app.ingest("gh_trending_repos")
    assert "row_count_floor" in broken.failed_assertions
    await app.loop.sweep_and_heal("gh_trending_repos")
    ledger = app.store.query(
        "SELECT before_state, after_state FROM heal_ledger WHERE verification_passed = TRUE"
    )
    assert ledger
    assert "row_count_floor" in (ledger[-1]["before_state"] or "")
    assert "row_count_floor" in (ledger[-1]["after_state"] or "")


@pytest.mark.asyncio
async def test_learning_reorders_playbook(app):
    await app.ingest("gh_trending_repos")
    app.break_source("gh_trending_repos", "http_403")
    await app.ingest("gh_trending_repos")
    first = await app.loop.sweep_and_heal("gh_trending_repos")
    assert first == ["healed"]
    app.contracts.patch("gh_trending_repos", {"_current_rung": 0})
    app.store.upsert_source_state("gh_trending_repos", current_rung=0)
    await app.ingest("gh_trending_repos")
    second = await app.loop.sweep_and_heal("gh_trending_repos")
    assert second == ["healed"]
    first_plan = app.store.query(
        "SELECT primitive FROM heal_ledger WHERE incident_id = (SELECT incident_id FROM incident ORDER BY detected_at LIMIT 1) ORDER BY attempt"
    )
    second_incident = app.store.query("SELECT incident_id FROM incident ORDER BY detected_at DESC LIMIT 1")[0][
        "incident_id"
    ]
    second_plan = app.store.query(
        "SELECT primitive FROM heal_ledger WHERE incident_id = ? ORDER BY attempt",
        [second_incident],
    )
    assert second_plan[0]["primitive"] == "P1"
    assert first_plan[0]["primitive"] == "P6"
