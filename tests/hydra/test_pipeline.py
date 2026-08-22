import pytest


@pytest.mark.asyncio
async def test_three_seed_sources_ingest(app):
    results = await app.ingest_all()
    assert [r.source_id for r in results] == [
        "amazon_products",
        "city_open_data",
        "crypto_prices_api",
        "gh_trending_repos",
    ]
    for result in results:
        assert result.status == "ok", (result.source_id, result.failed_assertions, result.error_message)
        assert result.rows_out >= 8
        assert result.snapshot_id
        assert app.store.count_raw(result.source_id) == 1


@pytest.mark.asyncio
async def test_raw_is_append_only(app):
    await app.ingest("crypto_prices_api")
    await app.ingest("crypto_prices_api")
    assert app.store.count_raw("crypto_prices_api") == 2
