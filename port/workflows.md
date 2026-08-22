# Port workflows

## Happy path

1. `factory run` upserts `factory_run` (validated) and later the service stays HEALTHY.
2. `factory port-sync` refreshes all four types from `data/state.json`.

## Break to recover

1. Scrape fails. `factory_run.status` becomes `invalid`. Service/scraper move to BROKEN.
2. `factory heal` creates an `approval` entity with `status=pending`.
3. `factory promote` exits 8 while that approval is pending. That is the gate.
4. A human runs `factory approve` (or clicks the same intent in Port). Approval becomes `approved`.
5. `factory run` again, same Collector ID. Service returns HEALTHY.

Reject sends approval to `rejected` and keeps promotion blocked.

Ledger lines with `remote_ok: false` are expected when Port credentials are missing. Flush them with `factory port-flush` after login works.
