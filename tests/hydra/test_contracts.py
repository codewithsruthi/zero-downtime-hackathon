from pathlib import Path

from hydra.contracts import ContractRegistry, load_meta_schema

ROOT = Path(__file__).resolve().parents[2]


def test_seed_contracts_validate():
    meta = load_meta_schema(ROOT / "contracts" / "_meta.schema.json")
    registry = ContractRegistry(ROOT / "contracts", meta_schema=meta)
    registry.load_seed()
    assert registry.ids() == ["city_open_data", "crypto_prices_api", "gh_trending_repos"]
    for cid in registry.ids():
        contract = registry.get(cid)
        assert len(contract["assertions"]) >= 3


def test_holdout_is_not_auto_loaded():
    registry = ContractRegistry(ROOT / "contracts")
    registry.load_seed()
    assert "surprise_source" not in registry.ids()
    registry.register_path(ROOT / "contracts" / "_holdout" / "surprise_source.json")
    assert "surprise_source" in registry.ids()
