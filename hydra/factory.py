from __future__ import annotations

import os
import threading
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
from hydra.live_snapshot import FAULTS_NAME, LIVE_NAME, write_snapshot
from hydra.mcp_pool import MCPPool
from hydra.runtime.acquire import Acquirer
from hydra.runtime.pipeline import Pipeline
from hydra.store import Store
from hydra.telemetry import init_telemetry, shutdown_telemetry


def _env_path(name: str) -> Path | None:
    raw = (os.environ.get(name) or "").strip()
    return Path(raw).expanduser().resolve() if raw else None


class HydraApp:
    def __init__(self, config: HydraConfig | None = None, *, db_path: str | Path | None = None):
        self.config = config or load_config()
        if db_path is not None:
            self.config.db_path = Path(db_path)
            self.data_dir = Path(db_path).parent
        else:
            self.data_dir = self.config.repo_root / "data"
        # Optional env overrides let the judge/live dashboard isolate state.
        # Unset keeps the replay sidecar: data/hydra-live.json (INV-1 still holds).
        self.faults_path = _env_path("HYDRA_FAULTS_PATH") or (self.data_dir / FAULTS_NAME)
        self.live_path = _env_path("HYDRA_LIVE_PATH") or (self.data_dir / LIVE_NAME)
        init_telemetry("hydra-ingestion", disabled=self.config.otel_disabled)
        self.store = Store(self.config.db_path)
        meta_path = self.config.contracts_dir / "_meta.schema.json"
        meta = load_meta_schema(meta_path) if meta_path.exists() else None
        self.contracts = ContractRegistry(self.config.contracts_dir, meta_schema=meta)
        self.contracts.load_seed()
        self.injector = ChaosInjector(persist_path=self.faults_path)
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
        self._op_lock = threading.RLock()

    def refresh_live(self, source_id: str | None = None):
        write_snapshot(self, source_id=source_id or "amazon_products")

    async def ingest(self, source_id: str):
        self._op_lock.acquire()
        try:
            result = await self.runtime.execute(self.contracts.get(source_id))
            self.refresh_live(source_id)
            return result
        finally:
            self._op_lock.release()

    async def heal_source(self, source_id: str | None = None):
        self._op_lock.acquire()
        try:
            resolutions = await self.loop.sweep_and_heal(source_id)
            self.refresh_live(source_id or "amazon_products")
            return resolutions
        finally:
            self._op_lock.release()

    async def ingest_all(self):
        results = []
        for source_id in self.contracts.ids():
            results.append(await self.ingest(source_id))
        return results

    def register(self, path: str | Path):
        return self.contracts.register_path(path)

    def break_source(self, source_id: str, fault: str, **cfg) -> None:
        with self._op_lock:
            self.injector.inject(source_id, fault, **cfg)
            self.refresh_live(source_id)

    def reset_circuit(self, source_id: str) -> None:
        with self._op_lock:
            self.store.reset_heal_window(source_id)
            self.store.upsert_source_state(
                source_id,
                circuit_state="closed",
                health="healthy",
                current_rung=0,
            )
            try:
                self.contracts.patch(source_id, {"_current_rung": 0})
            except Exception:
                pass
            self.refresh_live(source_id)

    def prepare_demo(self, source_id: str) -> None:
        """Keep the live dashboard from freezing on Guard during a presentation."""
        self.config.auto_approve_tier2 = True
        self.config.fingerprint_escalation = max(self.config.fingerprint_escalation, 20)
        try:
            self.contracts.patch(
                source_id,
                {"healing": {"heal_budget_per_hour": 25}, "_current_rung": 0},
            )
        except Exception:
            pass
        self.reset_circuit(source_id)

    def approve(self, incident_id: str) -> None:
        self.guard.approve(incident_id)
        self.refresh_live()

    def close(self) -> None:
        shutdown_telemetry()
        self.store.close()
