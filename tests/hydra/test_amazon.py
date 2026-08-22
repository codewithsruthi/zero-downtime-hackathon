from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_amazon_products_ingest_from_fixture(app):
    result = await app.ingest("amazon_products")
    assert result.status == "ok", (result.failed_assertions, result.error_message)
    assert result.rows_out >= 8
    rows = app.store.query("SELECT asin, title, price FROM derived_amazon_products")
    asins = {row["asin"] for row in rows}
    assert "B0CHHSFMRL" in asins
    assert all(row["title"] for row in rows)


def test_amazon_contract_points_at_brightdata_dataset():
    import json

    contract = json.loads((ROOT / "contracts" / "amazon_products.json").read_text())
    args = contract["acquisition"]["primary"]["args"]
    assert args["dataset_id"] == "gd_l7q7dkf244hwjntr0"
    assert args["collection_id"] == "hl_bbd9eb9a"
    assert contract["acquisition"]["kind"] == "structured_feed"
    assert contract["acquisition"]["primary"]["capability"] == "scrape_dataset"
