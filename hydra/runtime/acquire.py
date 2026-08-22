from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hydra.chaos.injector import ChaosInjector
from hydra.errors import AcquisitionError


@dataclass
class AcquireResult:
    payload: str
    http_status: int
    rung: int
    capability: str
    url: str | None
    media_type: str


class Acquirer:
    def __init__(
        self,
        *,
        fixtures_dir: Path,
        injector: ChaosInjector,
        pool=None,
        mode: str = "replay",
    ):
        self.fixtures_dir = Path(fixtures_dir)
        self.injector = injector
        self.pool = pool
        self.mode = mode

    async def acquire(self, contract: dict[str, Any], *, rung: int | None = None) -> AcquireResult:
        ladder = contract["acquisition"]["escalation_ladder"]
        current = contract.get("_current_rung", 0) if rung is None else rung
        current = max(0, min(current, len(ladder) - 1))
        capability = ladder[current]["capability"]
        primary = contract["acquisition"]["primary"]
        url = (primary.get("args") or {}).get("url")
        fixture_name = (primary.get("args") or {}).get("fixture") or contract["contract_id"]
        payload = self._load_fixture(fixture_name, capability)
        if payload is None and self.pool is not None and self.mode == "live":
            payload = await self.pool.invoke(capability if capability != "browser_session" else "fetch_html", url=url)
        if payload is None:
            raise AcquisitionError(
                f"no payload for {contract['contract_id']} at rung {current}",
                error_type="EmptyBody",
            )
        payload = self.injector.apply(contract["contract_id"], payload, rung=current)
        if not str(payload).strip():
            raise AcquisitionError("empty body", error_type="EmptyBody")
        if "Verify you are human" in str(payload) and "captcha" in str(payload).lower():
            raise AcquisitionError("captcha wall", error_type="CaptchaBlocked", http_status=403)
        media = "text/html" if capability in {"fetch_html", "browser_session"} else "text/plain"
        if str(payload).lstrip().startswith("{") or str(payload).lstrip().startswith("["):
            media = "application/json"
        elif "," in str(payload).split("\n", 1)[0] and "\n" in str(payload):
            media = "text/csv"
        return AcquireResult(
            payload=str(payload),
            http_status=200,
            rung=current,
            capability=capability,
            url=url,
            media_type=media,
        )

    def _load_fixture(self, name: str, capability: str) -> str | None:
        suffixes = [".md", ".json", ".csv", ".html"]
        if capability == "fetch_html":
            suffixes = [".html", ".md", ".json", ".csv"]
        for suffix in suffixes:
            path = self.fixtures_dir / f"{name}{suffix}"
            if path.exists():
                return path.read_text()
        return None
