# Troubleshooting

## Node is too old

`scripts/setup.sh` exits non-zero below Node 20. Use 20 or 22.

## `npm test` cannot find express

Run `./scripts/setup.sh`. The app and the CLI both import `express` from the repo root.

## Scrape fails in replay

`make reset` then check `data/sample-output/healthy.json` exists. `FACTORY_MODE` must be `replay`. A leftover `data/.broken` file forces the broken fixture.

## Promote exits 8

That is the approval gate. `factory status --json` should show `PENDING_APPROVAL` or `approval.status=rejected`. Approve, or `make reset`.

## Circuit open (exit 7)

Three failed scrapes in a row. `make reset` or `factory heal` then approve.

## App looks empty

HTTP 200 with "Waiting for the first successful promote" is legal. Run `factory run`. A stack dump is a bug.

## SigNoz is dark

Expected if the collector auth is blocked. The pipeline still finishes. Check `factory doctor` — the OTEL row should say the failure was swallowed.

## Port login is blocked

`port/state/ledger.jsonl` is the fallback. `factory port-sync` still exits 0.

## Bright Data CLI flag surprise

Edit only `src/adapters/brightdata/commands.js`. Record the difference at the bottom of `docs/cli-surface.md`.
