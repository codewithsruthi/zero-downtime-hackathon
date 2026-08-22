from __future__ import annotations

import argparse
import asyncio
import json
import sys

from hydra.factory import HydraApp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hydra", description="HYDRA self-healing data agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scrape = sub.add_parser("scrape", help="ingest one or all seed sources")
    p_scrape.add_argument("--source")

    p_break = sub.add_parser("break", help="inject a named fault")
    p_break.add_argument("--source", required=True)
    p_break.add_argument("--fault", required=True)
    p_break.add_argument("--permanent", action="store_true")
    p_break.add_argument("--from-field", dest="from_field")
    p_break.add_argument("--to-field", dest="to_field")
    p_break.add_argument("--field")
    p_break.add_argument("--rate", type=float)
    p_break.add_argument("--at", type=int)

    p_heal = sub.add_parser("heal", help="run one detect-and-heal sweep")
    p_heal.add_argument("--source")

    sub.add_parser("status", help="print source health and scoreboard")

    p_reg = sub.add_parser("register", help="register a contract JSON")
    p_reg.add_argument("path")

    p_ok = sub.add_parser("approve", help="approve a pending Tier 2 heal")
    p_ok.add_argument("--incident", required=True)

    p_reset = sub.add_parser("reset-circuit", help="close an open circuit")
    p_reset.add_argument("--source", required=True)

    sub.add_parser("demo", help="offline demo: ingest, break, heal")

    args = parser.parse_args(argv)
    app = HydraApp()
    try:
        return asyncio.run(_dispatch(app, args))
    finally:
        app.close()


async def _dispatch(app: HydraApp, args) -> int:
    if args.cmd == "scrape":
        if args.source:
            result = await app.ingest(args.source)
            _print_run(result)
            return 0 if result.status == "ok" else 1
        results = await app.ingest_all()
        for result in results:
            _print_run(result)
        return 0 if all(r.status == "ok" for r in results) else 1

    if args.cmd == "break":
        cfg = {}
        if args.permanent:
            cfg["permanent"] = True
        if args.from_field:
            cfg["from"] = args.from_field
        if args.to_field:
            cfg["to"] = args.to_field
        if args.field:
            cfg["field"] = args.field
        if args.rate is not None:
            cfg["rate"] = args.rate
        if args.at is not None:
            cfg["at"] = args.at
        app.break_source(args.source, args.fault, **cfg)
        print(f"injected {args.fault} on {args.source}")
        return 0

    if args.cmd == "heal":
        resolutions = await app.loop.sweep_and_heal(args.source)
        print(json.dumps({"resolutions": resolutions}, indent=2))
        return 0

    if args.cmd == "status":
        board = app.store.scoreboard()
        states = app.store.query("SELECT * FROM source_state")
        print(json.dumps({"sources": states, "scoreboard": board}, indent=2, default=str))
        return 0

    if args.cmd == "register":
        contract = app.register(args.path)
        print(f"registered {contract['contract_id']}")
        return 0

    if args.cmd == "approve":
        app.approve(args.incident)
        print(f"approved {args.incident}")
        return 0

    if args.cmd == "reset-circuit":
        app.reset_circuit(args.source)
        print(f"circuit closed for {args.source}")
        return 0

    if args.cmd == "demo":
        return await _demo(app)

    return 2


async def _demo(app: HydraApp) -> int:
    print("== happy path ==")
    for result in await app.ingest_all():
        _print_run(result)
    print("== break gh_trending_repos with http_403 ==")
    app.break_source("gh_trending_repos", "http_403")
    broken = await app.ingest("gh_trending_repos")
    _print_run(broken)
    print("== heal ==")
    print(await app.loop.sweep_and_heal("gh_trending_repos"))
    return 0


def _print_run(result) -> None:
    print(
        f"{result.source_id}: {result.status} rows={result.rows_out} "
        f"failed={result.failed_assertions} err={result.error_type}"
    )


if __name__ == "__main__":
    sys.exit(main())
