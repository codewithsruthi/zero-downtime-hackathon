# Port brief

Four entity types tell the governance story:

- service — the digest app
- scraper — the Bright Data collector (`c_hn_digest_factory`)
- factory_run — one scrape → validate → promote attempt
- approval — the human gate that blocks `factory promote`

The factory writes every upsert to `port/state/ledger.jsonl` first. If Port login is blocked, the ledger is still the demo artifact. `factory port-flush` retries remotes later.

The approval entity is the thing a judge should look at between `factory heal` and `factory approve`. Promotion stays blocked while that entity is `pending` or `rejected`.
