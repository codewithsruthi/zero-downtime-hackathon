#!/usr/bin/env python3
"""Startup probe. Replay checks local bindings. Live also lists MCP tools."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hydra.config import load_config
from hydra.contracts import ContractRegistry, load_meta_schema
from hydra.mcp_pool import MCPPool, probe_capabilities
from hydra.store import Store


async def main() -> int:
    cfg = load_config(ROOT)
    errors = []

    store = Store(cfg.db_path)
    try:
        store.query("SELECT 1")
        print("  OK  duckdb       schema initialized")
    except Exception as exc:
        print(f"  FAIL duckdb       {exc}")
        errors.append("duckdb")
    finally:
        store.close()

    meta = load_meta_schema(cfg.contracts_dir / "_meta.schema.json")
    registry = ContractRegistry(cfg.contracts_dir, meta_schema=meta)
    try:
        registry.load_seed()
        holdout = cfg.contracts_dir / "_holdout" / "surprise_source.json"
        extra = " + 1 holdout" if holdout.exists() else ""
        print(f"  OK  contracts    {len(registry.ids())} seed{extra} valid")
    except Exception as exc:
        print(f"  FAIL contracts    {exc}")
        errors.append("contracts")

    pool = MCPPool(
        capabilities_path=cfg.capabilities_path,
        mode=cfg.mode,
        fixtures_dir=cfg.fixtures_dir,
    )
    try:
        lines = await probe_capabilities(pool)
        for line in lines:
            print(line)
        print(f"  OK  capabilities {len(pool.caps)} bindings loaded")
    except Exception as exc:
        print(f"  FAIL capabilities {exc}")
        errors.append("capabilities")

    if errors:
        print(f"probe failed: {', '.join(errors)}")
        return 1
    print(f"All {len(pool.caps)} capability bindings resolved ({cfg.mode}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
