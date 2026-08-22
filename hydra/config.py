from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    override = os.environ.get("HYDRA_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parent.parent


def load_dotenv(root: Path | None = None) -> None:
    path = (root or _repo_root()) / ".env"
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


@dataclass
class HydraConfig:
    mode: str
    env_name: str
    repo_root: Path
    db_path: Path
    contracts_dir: Path
    fixtures_dir: Path
    capabilities_path: Path
    playbooks_path: Path
    detect_interval_s: float
    heal_budget_per_hour: int
    fingerprint_escalation: int
    max_attempts_per_incident: int
    approval_timeout_s: float
    auto_approve_tier2: bool
    backoff_base_s: float
    otel_disabled: bool

    @property
    def replay(self) -> bool:
        return self.mode != "live"


def load_config(repo_root: Path | None = None) -> HydraConfig:
    root = Path(repo_root).resolve() if repo_root else _repo_root()
    load_dotenv(root)
    mode = os.environ.get("HYDRA_MODE", "replay").strip().lower()
    db = Path(os.environ.get("HYDRA_DB_PATH", str(root / "hydra.duckdb")))
    return HydraConfig(
        mode=mode,
        env_name=os.environ.get("HYDRA_ENV", "hackathon"),
        repo_root=root,
        db_path=db,
        contracts_dir=root / "contracts",
        fixtures_dir=root / "fixtures",
        capabilities_path=root / "capabilities.yaml",
        playbooks_path=root / "playbooks.yaml",
        detect_interval_s=float(os.environ.get("HYDRA_DETECT_INTERVAL_S", "15")),
        heal_budget_per_hour=int(os.environ.get("HYDRA_HEAL_BUDGET_PER_HOUR", "5")),
        fingerprint_escalation=int(os.environ.get("HYDRA_FINGERPRINT_ESCALATION", "3")),
        max_attempts_per_incident=int(os.environ.get("HYDRA_MAX_ATTEMPTS_PER_INCIDENT", "4")),
        approval_timeout_s=float(os.environ.get("HYDRA_APPROVAL_TIMEOUT_S", "300")),
        auto_approve_tier2=os.environ.get("HYDRA_AUTO_APPROVE_TIER2", "") == "1",
        backoff_base_s=float(os.environ.get("HYDRA_BACKOFF_BASE_S", "0")),
        otel_disabled=os.environ.get("HYDRA_OTEL_DISABLED", "") == "1"
        or os.environ.get("FACTORY_OTEL_DISABLED", "") == "1",
    )
