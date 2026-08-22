from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


class MCPPool:
    """Resolve logical capabilities. Live MCP is optional; replay uses fixtures."""

    def __init__(
        self,
        *,
        capabilities_path: str | Path,
        mode: str = "replay",
        fixtures_dir: str | Path | None = None,
        on_invoke=None,
    ):
        self.mode = mode
        self.caps = yaml.safe_load(Path(capabilities_path).read_text())["capabilities"]
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else None
        self.on_invoke = on_invoke
        self.sessions: dict[str, Any] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "MCPPool":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def list_tools(self, server: str) -> list[Any]:
        names = sorted({spec["tool"] for spec in self.caps.values() if spec.get("server") == server})

        class Tool:
            def __init__(self, name: str):
                self.name = name

        return [Tool(n) for n in names]

    async def invoke(self, capability: str, **kwargs: Any) -> Any:
        spec = self.caps.get(capability)
        if spec is None:
            raise KeyError(f"Unknown capability {capability!r}. Check capabilities.yaml.")
        args = _bind_args(spec.get("args") or {}, kwargs)
        for key, value in kwargs.items():
            args.setdefault(key, value)
        self.calls.append((capability, args))
        if self.on_invoke is not None:
            return await _maybe_await(self.on_invoke(capability, args, spec))
        if self.mode != "live":
            return self._replay(capability, args)
        raise RuntimeError(
            f"live invoke of {capability} is not wired in this process; use Cursor MCP or set a stub"
        )

    def _replay(self, capability: str, args: dict[str, Any]) -> Any:
        if capability == "scrape_dataset":
            slug = str(args.get("fixture") or args.get("dataset_id") or "amazon_products")
            if self.fixtures_dir:
                for name in (slug, "amazon_products"):
                    path = self.fixtures_dir / f"{name}.json"
                    if path.exists():
                        return path.read_text()
            return "[]"
        if capability in {"fetch_markdown", "fetch_html", "ai_extract", "browser_get_html"}:
            url = str(args.get("url") or "")
            return self._fixture_for_url(url, html=capability != "fetch_markdown")
        if capability == "find_alternate_source":
            return {"results": []}
        if capability == "quota_check":
            return {"requests": 0}
        if capability.startswith("catalog_") or capability.startswith("governance_"):
            return []
        if capability in {"find_error_traces", "search_logs", "active_alerts", "list_services"}:
            return []
        return None

    def _fixture_for_url(self, url: str, *, html: bool) -> str:
        if self.fixtures_dir is None:
            return ""
        slug = url.rstrip("/").split("/")[-1] or "page"
        candidates = []
        if html:
            candidates.append(self.fixtures_dir / f"{slug}.html")
        candidates.append(self.fixtures_dir / f"{slug}.md")
        candidates.append(self.fixtures_dir / f"{slug}.json")
        candidates.append(self.fixtures_dir / f"{slug}.csv")
        for path in candidates:
            if path.exists():
                return path.read_text()
        return ""


def load_capabilities(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())["capabilities"]


def _bind_args(templates: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for key, template in templates.items():
        if isinstance(template, str) and template.startswith("{") and template.endswith("}"):
            args[key] = kwargs.get(template[1:-1])
        else:
            args[key] = template
    return args


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


async def probe_capabilities(pool: MCPPool, caps: dict[str, Any] | None = None) -> list[str]:
    """Fail loudly at startup, never mid-heal. Replay always resolves from YAML."""
    spec = caps or pool.caps
    available: dict[str, set[str]] = {}
    for server_name in ("port", "signoz", "brightdata"):
        tools = await pool.list_tools(server_name)
        available[server_name] = {t.name for t in tools}
    missing = [
        (cap, item["server"], item["tool"])
        for cap, item in spec.items()
        if item["tool"] not in available.get(item["server"], set())
    ]
    lines = []
    if missing:
        for cap, srv, tool in missing:
            lines.append(f"  MISSING  {cap:28s} -> {srv}:{tool}")
        raise RuntimeError(
            f"{len(missing)} capability bindings unresolved. Update capabilities.yaml."
        )
    for srv, tools in available.items():
        lines.append(f"  OK  {srv:12s} {len(tools)} tools")
    return lines
