# Zero Downtime Factory — operator rules

SCRAPER_STUDIO_COLLECTOR_ID=c_hn_digest_factory
HACKER_NEWS_SCRAPER_USAGE="bdata scraper run $SCRAPER_STUDIO_COLLECTOR_ID https://news.ycombinator.com --pretty"

## Invariants

INV-1: `data/latest.json` is absent or a valid, schema-conformant, quality-gated document. Never write Bright Data CLI output straight there. Raw goes to `data/raw/run-<id>.json`, then normalise, validate, atomic promote.

Heal is triggered. Never automatic. Do not pass `--auto-approve` to `bdata scraper heal`.

Reuse the same Collector ID after heal. Do not create a second scraper for the demo.

Port writes must hit the local ledger first. A Port login failure does not fail the pipeline.

OTEL export failures are swallowed (3s timeout, log once). Service name is `zero-downtime-factory`. `factory.component` is `app` or `pipeline`.

Default mode is `FACTORY_MODE=replay`. Live mode needs `BRIGHTDATA_API_KEY`.

## Commands

```
./bin/factory scrape|validate|heal|approve|reject|promote|rollback|status|break|run|port-sync|port-flush|doctor
make demo-offline
```
