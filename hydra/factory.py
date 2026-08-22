from __future__ import annotations

from pathlib import Path

from hydra.agent.detector import Detector
from hydra.agent.executor import Executor
from hydra.agent.guard import Guard
from hydra.agent.ledger import Ledger
from hydra.agent.loop import HealingLoop
from hydra.agent.proposer import Proposer
from hydra.agent.verifier import Verifier
from hydra.chaos.injector import ChaosInjector
from hydra.config import HydraConfig, load_config
from hydra.contracts import ContractRegistry, load_meta_schema
from hydra.mcp_pool import MCPPool
from hydra.runtime.acquire import Acquirer
from hydra.runtime.pipeline import Pipeline
from hydra.store import Store
from hydra.telemetry import init_telemetry


class HydraApp:
    def __init__(self, config: HydraConfig | None = None, *, db_path: str | Path | None = None):
        self.config = config or load_config()
        if db_path is not None:
            self.config.db_path = Path(db_path)
        init_telemetry("hydra-ingestion", disabled=self.config.otel_disabled)
        self.store = Store(self.config.db_path)
        meta_path = self.config.contracts_dir / "_meta.schema.json"
        meta = load_meta_schema(meta_path) if meta_path.exists() else None
        self.contracts = ContractRegistry(self.config.contracts_dir, meta_schema=meta)
        self.contracts.load_seed()
        self.injector = ChaosInjector()
        self.pool = MCPPool(
            capabilities_path=self.config.capabilities_path,
            mode=self.config.mode,
            fixtures_dir=self.config.fixtures_dir,
        )
        self.acquirer = Acquirer(
            fixtures_dir=self.config.fixtures_dir,
            injector=self.injector,
            pool=self.pool,
            mode=self.config.mode,
        )
        self.runtime = Pipeline(self.store, self.acquirer, self.contracts)
        self.detector = Detector(self.pool, self.store, self.contracts)
        self.proposer = Proposer(self.config.playbooks_path, self.store)
        self.guard = Guard(self.pool, self.store, self.config)
        self.executor = Executor()
        self.verifier = Verifier(self.store, self.runtime)
        self.ledger = Ledger(self.store, self.pool)
        self.loop = HealingLoop(
            self.pool,
            self.store,
            self.contracts,
            self.detector,
            self.proposer,
            self.guard,
            self.executor,
            self.verifier,
            self.ledger,
            self.runtime,
            self.injector,
            self.config,
        )

    async def ingest(self, source_id: str):
        return await self.runtime.execute(self.contracts.get(source_id))

    async def ingest_all(self):
        results = []
        for source_id in self.contracts.ids():
            results.append(await self.ingest(source_id))
        return results

    def register(self, path: str | Path):
        return self.contracts.register_path(path)

    def break_source(self, source_id: str, fault: str, **cfg) -> None:
        self.injector.inject(source_id, fault, **cfg)

    def reset_circuit(self, source_id: str) -> None:
        self.store.upsert_source_state(source_id, circuit_state="closed", health="healthy")

    def approve(self, incident_id: str) -> None:
        self.guard.approve(incident_id)

    def close(self) -> None:
        self.store.close()
