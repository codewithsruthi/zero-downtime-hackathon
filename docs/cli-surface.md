# Bright Data CLI surface

Captured: 2026-08-22T04:39:26Z
Node: v22.22.1
Pinned package: @brightdata/cli@0.3.5

If the live surface differs from the assumed flags, edit ONLY
src/adapters/brightdata/commands.js (EC-PROBE-01).

## node --version

```
v22.22.1
```

## npx -p @brightdata/cli@0.3.5 bdata --help

```
Usage: brightdata [options] [command]

Command-line interface for Bright Data. Scrape, search, extract structured data,
and automate browsers from your terminal.

Options:
  -v, --version                           output the version number
  -k, --api-key <key>                     Bright Data API key (overrides env/config)
  --timing                                Show request timing
  -h, --help                              display help for command

Commands:
  login [options]                         Authenticate with Bright Data (opens browser)
  logout                                  Clear stored Bright Data credentials
  scrape [options] <url>                  Scrape a URL using the Web Unlocker API
  search [options] <query>                Search the web using the SERP API
  pipelines [options] <type> [params...]  Extract structured data using Bright Data Pipelines
  status [options] <job-id>               Check status of an async Web Scraper snapshot job
  zones [options]                         List and inspect Bright Data zones
  config [options]                        View and edit CLI configuration
  init [options]                          Interactive setup wizard for authentication and defaults
  version [options]                       Display CLI version information
  skill                                   Manage Bright Data agent skills
  budget [options]                        View account balance and zone spending
  browser [options]                       Control Bright Data browser sessions
  discover [options] <query>              Search and rank web results using AI-driven intent
  scraper                                 Build and manage Bright Data scrapers
  add                                     Add Bright Data integrations to supported coding agents
  help [command]                          display help for command
```

## npx -p @brightdata/cli@0.3.5 bdata scraper --help

```
Usage: brightdata scraper [options] [command]

Build and manage Bright Data scrapers

Options:
  -h, --help                              display help for command

Commands:
  create [options] <url> <description>    Build a scraper from a natural-language description using AI
  run [options] <collector_id> [url]      Run a Bright Data scraper on one or more URLs and return the data
  heal [options] <collector_id> <prompt>  Fix an existing scraper in place via AI self-healing
  approve [options] <collector_id>        Approve (or --reject) a heal that is awaiting approval
  help [command]                          display help for command
```

## npx -p @brightdata/cli@0.3.5 bdata scraper create --help

```
Usage: brightdata scraper create [options] <url> <description>

Build a scraper from a natural-language description using AI

Arguments:
  url                      Target URL to scrape
  description              Natural-language description of data to extract (max
                           500 chars)

Options:
  --name <name>            Scraper template name (default:
                           cli-scraper-<timestamp>)
  --deliver-webhook <url>  Webhook URL for the deliver stub (default:
                           https://example.com/webhook)
  --timeout <seconds>      Polling timeout in seconds (default: 600)
  --max-retries <n>        Max retries on the AI-Flow concurrent-job cap 429
                           (default: 4). Each wait grows exponentially with
                           jitter, up to ~4 min between attempts.
  --no-retry               Fail immediately on 429 instead of waiting through
                           the cap. Equivalent to --max-retries 0.
  -o, --output <path>      Write output to file
  --json                   Force JSON output
  --pretty                 Pretty-print JSON output
  --legacy-output          Emit the bare AI-progress payload (pre-v0.3 shape)
                           instead of the new {collector_id, name, status, ...}
                           envelope. For one-version migration only.
  --timing                 Show request timing
  -h, --help               display help for command

Examples:
  # Build a scraper for a public page (AI generation takes 5 to 10 minutes)
  $ brightdata scraper create https://news.ycombinator.com "Extract the top 30 stories: title, url, points, author, comment count."

  # Name the scraper and save the full AI output for inspection
  $ brightdata scraper create https://www.ycombinator.com/companies?batch=W26 "For each company card, extract name, vertical, tagline, link" --name yc-w26 --pretty -o create.json

  # Custom delivery webhook (default is a stub, set this when wiring to your own backend)
  $ brightdata scraper create https://news.ycombinator.com "Extract top stories" --deliver-webhook https://your-app.test/scraper-callback

```

## npx -p @brightdata/cli@0.3.5 bdata scraper run --help

```
Usage: brightdata scraper run [options] <collector_id> [url]

Run a Bright Data scraper on one or more URLs and return the data

Arguments:
  collector_id              Collector ID of the scraper (returned by `scraper
                            create`)
  url                       URL to scrape. Omit when using --urls or
                            --input-file.

Options:
  --urls <list>             Comma-separated list of URLs. Mirror of
                            triggerWithUrls / trigger_with_urls from the Bright
                            Data Scraper Studio reference SDKs. Routes via
                            /dca/trigger as a single batch.
  --input-file <path>       Path to a file with URLs: one per line (# comments
                            and blank lines skipped), OR a JSON array of
                            strings, OR a JSON array of {"url": "..."} objects.
  --sync                    Use the synchronous /dca/crawl endpoint (server-side
                            25-50s cap). Single-URL only.
  --sync-timeout <seconds>  Sync-mode server timeout (25-50, default 50)
  --timeout <seconds>       Polling timeout in async mode (default: 600; batch
                            mode: 3600)
  --name <name>             Human-readable job name
  --version <version>       Scraper version (e.g. "dev")
  -o, --output <path>       Write output to file
  --json                    Force JSON output
  --pretty                  Pretty-print JSON output
  --timing                  Show request timing
  -h, --help                display help for command

Examples:
  # Run a scraper against a single URL (async, polls until done)
  $ brightdata scraper run c_mp3tuab31lswoxvpws https://news.ycombinator.com --pretty

  # Sync mode for small fast pages (server-side 25 to 50 second cap)
  $ brightdata scraper run c_mp3tuab31lswoxvpws https://news.ycombinator.com --sync

  # Save output as CSV (extension chooses format)
  $ brightdata scraper run c_mp3tuab31lswoxvpws https://news.ycombinator.com -o stories.csv

```

## npx -p @brightdata/cli@0.3.5 bdata scraper heal --help

```
Usage: brightdata scraper heal [options] <collector_id> <prompt>

Fix an existing scraper in place via AI self-healing

Arguments:
  collector_id         Collector ID of the scraper to fix (from `scraper
                       create`)
  prompt               What is broken / what to fix (max 1000 chars)

Options:
  --url <url>          Verify target woven into the next-step hint. Not sent to
                       the heal call; heal only mutates the scraper.
  --auto-approve       When the heal hits the approval gate, approve it
                       automatically and poll through to done (default: stop and
                       let you review).
  --auto-save          With --auto-approve, also save the healed template
                       automatically once the job completes (sent as auto_save
                       to the resume call).
  --timeout <seconds>  Polling timeout in seconds (default: 600)
  --max-retries <n>    Max retries on the AI-Flow concurrent-job cap 429
                       (default: 4). Each wait grows exponentially with jitter,
                       up to ~4 min between attempts.
  --no-retry           Fail immediately on 429 instead of waiting through the
                       cap. Equivalent to --max-retries 0.
  -o, --output <path>  Write output to file
  --json               Force JSON output
  --pretty             Pretty-print JSON output
  --legacy-output      Emit the bare AI-progress payload instead of the
                       {collector_id, status, prompt, next_step, ...} envelope.
  --timing             Show request timing
  -h, --help           display help for command

Examples:
  # Fix a scraper whose price selector drifted, then get a ready-to-run verify command back
  $ brightdata scraper heal c_mp3tuab31lswoxvpws "The price field returns null — the selector moved into a span with data-testid. Capture price and currency again." --url https://example.com/product/1

  # Heal and save the result envelope (next_step tells you how to verify)
  $ brightdata scraper heal c_mp3tuab31lswoxvpws "Reviews stopped extracting after the page redesign" --pretty -o heal.json

```

## npx -p @brightdata/cli@0.3.5 bdata scraper approve --help

```
Usage: brightdata scraper approve [options] <collector_id>

Approve (or --reject) a heal that is awaiting approval

Arguments:
  collector_id         Collector ID of the scraper whose heal is awaiting
                       approval

Options:
  --reject             Reject the proposed fix instead of approving it.
  --auto-save          Save the approved template automatically once the job
                       completes successfully (sent as auto_save to the resume
                       call).
  --url <url>          Verify target woven into the next-step hint on success.
  --timeout <seconds>  Polling timeout in seconds (default: 600)
  -o, --output <path>  Write output to file
  --json               Force JSON output
  --pretty             Pretty-print JSON output
  --legacy-output      Emit the bare AI-progress payload instead of the
                       envelope.
  --timing             Show request timing
  -h, --help           display help for command

Examples:
  # Approve a heal that stopped at awaiting_approval, then verify
  $ brightdata scraper approve c_mp3tuab31lswoxvpws --url https://example.com/product/1

  # Reject a proposed fix and start over with a sharper heal prompt
  $ brightdata scraper approve c_mp3tuab31lswoxvpws --reject

```

## Resolved version

```
0.3.5
```

## Deviations from the source-doc assumed flags

Pinned version: **0.3.5** (npm `latest` at probe time). `heal` / `approve` shipped in 0.3.1.

Assumed `create` / `run` / `heal` / `approve` flag shapes match the live CLI. `-o` and `--pretty` exist on `scraper run`.

Deviations encoded only in `src/adapters/brightdata/commands.js`:

1. **Reject is not a subcommand.** Live CLI: `bdata scraper approve <collector_id> --reject`. `CLI.reject` appends `--reject` to the approve argv. Factory still exposes `factory reject`.
2. **Do not pass `--auto-approve` on heal.** The live CLI has it. DEC-07 forbids automatic heal approval, so the adapter never sends that flag.
3. Probe used `@brightdata/cli@0.3.5`, not an unpinned `@brightdata/cli` (EC-PROBE-02).
