# Demo runbook

Rehearse this offline. Venue wifi is not part of the act.

## Setup once

```bash
./scripts/setup.sh
make demo-offline
```

That run should print `DEMO_OK`. If it does not, see TROUBLESHOOTING.md.

## Live five minutes

Keep one TRACEPARENT for the whole story so SigNoz shows a single trace.

```bash
export FACTORY_MODE=replay
export TRACEPARENT=00-$(openssl rand -hex 16)-$(openssl rand -hex 8)-01
make reset
make app
```

In a second terminal:

1. `./bin/factory run` — digest lists stories.
2. Open `http://127.0.0.1:3000`. Leave it up.
3. `./bin/factory break` then `./bin/factory scrape` — scrape fails, page still shows the last list.
4. `./bin/factory heal` — state is `PENDING_APPROVAL`. `./bin/factory promote` exits 8.
5. Point at Port (or `port/state/ledger.jsonl`) for the pending approval.
6. `./bin/factory approve` then `./bin/factory run` — same `c_hn_digest_factory`, stories refresh.

Do not create a second collector. Do not pass `--auto-approve`.

## Live Bright Data (optional)

Set `BRIGHTDATA_API_KEY` and `FACTORY_MODE=live`. Put the real `c_*` in CLAUDE.md and `agent-rules/scraper.md`. Warm the CLI with `npx -p @brightdata/cli@0.3.5 bdata --version` before anyone is watching.
