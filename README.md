# Zero Downtime Factory

A governed factory that feeds a Hacker News digest. When the scrape breaks, you heal it with Bright Data, a human approves the fix in Port, SigNoz shows the same trace, and the app keeps serving the last good list.

The factory is the product. The digest is the test run.

Collector ID (do not rotate during a demo):

```
SCRAPER_STUDIO_COLLECTOR_ID=c_hn_digest_factory
```

## Setup

Node 20+.

```bash
./scripts/setup.sh
npm test
make demo-offline
```

`FACTORY_MODE` defaults to `replay`, so the demo does not need venue wifi or a Bright Data login.

## Commands

```bash
./bin/factory scrape|validate|heal|approve|reject|promote|rollback|status|break|run|port-sync|port-flush|doctor
make app          # digest on :3000
make reset
make demo-offline
```

Global flags: `--json` `--verbose` `--dry-run` `--collector-id` `--url`.

## Appendix A — exit codes

| Code | Name |
|:--|:--|
| 0 | SUCCESS |
| 1 | GENERIC |
| 2 | CONFIG |
| 3 | ILLEGAL_TRANSITION |
| 4 | VALIDATION |
| 5 | SCRAPE |
| 6 | LOCK |
| 7 | CIRCUIT |
| 8 | NOT_APPROVED |
| 9 | HEAL |
| 10 | PARSE |
| 11 | FILE |
| 12 | USAGE |

## Definition of done

- [x] Layout matches SPEC.md 4.1
- [x] `docs/cli-surface.md` has real `--help` from `@brightdata/cli@0.3.5`
- [x] INV-1: CLI never writes scrape output onto `data/latest.json`
- [x] Replay fixtures let `make demo-offline` finish without network
- [x] Job posts pass validation (EC-DATA-01)
- [x] Approval gate blocks promote (exit 8)
- [x] Same Collector ID across break → heal → approve → re-run
- [x] Port ledger survives a dead remote
- [x] OTEL export failures are swallowed
- [x] Digest stays on HTTP 200 during a break
- [x] Every TEST-* in Section 11 exists under `tests/`

See SPEC.md and plan.md for the full contract.

## HYDRA

Source-agnostic healing lives in `hydra/`. Contracts are JSON. Failures map to six classes. The existing factory and `data/latest.json` are untouched.

```
pip install -r requirements-hydra.txt
make hydra-probe
make hydra-test
python3 -m hydra scrape
python3 -m hydra break --source gh_trending_repos --fault http_403
python3 -m hydra heal --source gh_trending_repos
```

Design: `HYDRA.md`. Default `HYDRA_MODE=replay`.
