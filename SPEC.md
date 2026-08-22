# Zero Downtime Factory: Implementation Specification

**Version:** 1.0
**Source:** "Zero Downtime Factory: Full Project Spec" (Google Doc)
**Audience:** Claude Code / Cursor, executing against an empty repository
**Repo name:** `zero-downtime-factory`

---

## How to use this document

This is the single source of truth for implementation. Every requirement has a stable ID.

| Prefix | Meaning |
|:--|:--|
| `REQ-*` | Functional requirement |
| `EC-*` | Edge case with mandatory handling |
| `TEST-*` | Test that must exist and pass |
| `DEC-*` | Design decision, already made, do not re-litigate |
| `P0 / P1 / P2` | Priority. P0 = demo dies without it. P1 = judges notice. P2 = polish. |

**Agent instructions:** implement phase by phase (Section 14). Do not skip the probe phase. After each phase, run the acceptance command listed and stop if it fails. When a decision is ambiguous and this document does not cover it, prefer the option that keeps `data/latest.json` valid and the app responding.

---

## 1. Product definition

### 1.1 What is being built

A governed agentic factory that produces and continuously feeds a live Hacker News digest. When the source site changes, the pipeline detects the break, heals via Bright Data, records the event in Port behind a human approval gate, surfaces every step in SigNoz, and resumes without the app going dark.

**The factory is the product. The digest app is the test run.** Design decisions that make the factory more legible to a judge beat decisions that make the digest app prettier.

### 1.2 The single non-negotiable invariant

> **INV-1: `data/latest.json` is always either absent or a valid, schema-conformant, quality-gated document. It is never partially written, never contains failed-scrape output, and is never mutated by a run that did not pass validation.**

Everything in Section 5 (state machine) and Section 6 (data contracts) exists to protect INV-1. If an implementation choice threatens INV-1, it is wrong.

### 1.3 Non-goals

- Pretty UI. A clean list is sufficient. Do not add a component library, dark mode toggle, or animations.
- Authentication on the digest app.
- A database. Files are the store. SQLite is explicitly out of scope for the hackathon window.
- Real-time push (WebSockets/SSE). Polling is sufficient.
- Multi-source scraping. Hacker News only.
- Historical analytics on stories.

### 1.4 Success criteria (judge-visible)

| Track | Must be demonstrable live |
|:--|:--|
| Bright Data | Terminal-only workflow, stable Collector ID read from the agent rules file, clean JSON, working break to heal to approve to re-run with the **same** Collector ID |
| Port | Four entity types populated, a human approval gate that visibly blocks promotion, MCP used by the coding agent |
| SigNoz | One trace spanning run to heal to approve to re-run, heal and failure as first-class signals, one dashboard with latency, throughput, errors |
| Overall | The app never returns an error page or empty screen at any point during the break demo |

---

## 2. Decisions already made

| ID | Decision | Rationale |
|:--|:--|:--|
| `DEC-01` | **Node.js 20+ for everything.** App is Express. Pipeline is a Node CLI. | The Bright Data CLI is Node. One toolchain means one OTEL setup, trivial in-process trace context propagation, and no cross-language glue at 15:00 on demo day. A FastAPI variant is specified in Appendix C if you insist, but it costs roughly 45 minutes and buys nothing the judges score. |
| `DEC-02` | **The Bright Data CLI is wrapped behind an adapter**, never invoked inline from business logic. | The exact flag surface of `@brightdata/cli` is unverified. A single adapter file localises the blast radius of a wrong flag to one edit. |
| `DEC-03` | **Three data modes: `live`, `record`, `replay`.** | The demo must be rehearsable offline and deterministic. Venue wifi, rate limits, and HN outages are all real. |
| `DEC-04` | **CLI output never writes directly to `data/latest.json`.** The source doc's `-o data/latest.json` is a bug. Raw output lands in `data/raw/run-<runId>.json`, then normalise, then validate, then atomically promote. | Direct write violates INV-1. A failed scrape would blank the app on stage. |
| `DEC-05` | **Port writes are mirrored to a local append-only ledger and are never allowed to fail the pipeline.** | The source doc flags Port corporate login as a risk. A blocked login must degrade the governance story, not kill the demo. |
| `DEC-06` | **OTEL export failures are swallowed, capped at a 3 second timeout, and logged once.** | SigNoz auth is flagged as blocked. A hanging exporter on stage is unacceptable. |
| `DEC-07` | **Heal is triggered, never automatic.** | Explicit requirement from the source doc and the entire point of the Port approval gate. |
| `DEC-08` | **Single OTEL service name `zero-downtime-factory`**, with a `factory.component` attribute (`app` or `pipeline`) to separate concerns. | One service means one dashboard, which is what the SigNoz track asks for. |

---

## 3. Phase 0: Capability probe (do this first, P0)

The commands in the source document are **assumed, not verified**. Before writing any adapter logic, establish ground truth.

### `REQ-PROBE-01` (P0)
Create `scripts/probe.sh` that runs and tees output to `docs/cli-surface.md`:

```bash
node --version
npx -p @brightdata/cli bdata --help          || true
npx -p @brightdata/cli bdata scraper --help  || true
npx -p @brightdata/cli bdata scraper create --help || true
npx -p @brightdata/cli bdata scraper run --help    || true
npx -p @brightdata/cli bdata scraper heal --help   || true
npx -p @brightdata/cli bdata scraper approve --help || true
```

### `REQ-PROBE-02` (P0)
Record findings in `src/adapters/brightdata/commands.js` as a declarative map. This is the **only** file that encodes CLI syntax:

```js
// src/adapters/brightdata/commands.js
// SINGLE SOURCE OF TRUTH for Bright Data CLI syntax.
// If the CLI surface differs from the probe, edit ONLY this file.
export const CLI = {
  bin: 'npx',
  baseArgs: ['-p', '@brightdata/cli@<PINNED_VERSION>', 'bdata'],
  create: ({ url, prompt }) => ['scraper', 'create', url, prompt],
  run:    ({ collectorId, url, outPath }) =>
            ['scraper', 'run', collectorId, url, '--pretty', '-o', outPath],
  heal:   ({ collectorId, prompt, url }) =>
            ['scraper', 'heal', collectorId, prompt, '--url', url],
  approve:({ collectorId, url }) =>
            ['scraper', 'approve', collectorId, '--url', url],
};
```

### `EC-PROBE-01` (P0)
**Trigger:** a subcommand in the source doc does not exist, or flags differ.
**Behaviour:** update `commands.js`, note the deviation in `docs/cli-surface.md`, and continue. Do not rewrite call sites.

### `EC-PROBE-02` (P0)
**Trigger:** `npx -p @brightdata/cli` triggers a multi-second package download on first invocation, mid-demo.
**Behaviour:** pin the version and pre-warm during setup. Add to `scripts/setup.sh`:
```bash
npx -p @brightdata/cli@<PINNED_VERSION> bdata --version   # warms the npx cache
```
Record the resolved version in `docs/cli-surface.md`. Never use an unpinned `@brightdata/cli` in a demo path.

### `EC-PROBE-03` (P1)
**Trigger:** the CLI writes progress or banner text to stdout alongside JSON, or writes JSON to stdout instead of honouring `-o`.
**Behaviour:** the adapter must handle both. After invocation: if `outPath` exists and parses, use it. Otherwise attempt to extract the first balanced JSON value from stdout (scan for the first `[` or `{`, then bracket-match). If neither yields valid JSON, classify as `FAIL_PARSE`.

### `EC-PROBE-04` (P0)
**Trigger:** Node version is below 20.
**Behaviour:** `scripts/setup.sh` exits non-zero with an explicit message. Add `"engines": { "node": ">=20" }` to both `package.json` files.

**Acceptance:** `docs/cli-surface.md` exists and contains real `--help` output. `commands.js` reflects it.

---

## 4. Architecture

```
                    ┌──────────────────────────────┐
                    │  Port (intent + approvals)   │
                    │  service / scraper /         │
                    │  factory_run / approval      │
                    └───────┬──────────────┬───────┘
                            │ MCP or REST  │ mirror (always)
                            ▼              ▼
                    ┌──────────────────────────────┐
                    │  factory CLI  (bin/factory)  │
                    │  probe scrape validate heal  │
                    │  approve promote rollback    │
                    └───────┬──────────────────────┘
                            │
              ┌─────────────┴──────────────┐
              ▼                            ▼
   ┌────────────────────┐      ┌──────────────────────┐
   │ Bright Data adapter│      │ port/state/*.jsonl   │
   │ live/record/replay │      │ local ledger fallback│
   └─────────┬──────────┘      └──────────────────────┘
             │
             ▼
   data/raw/run-<id>.json
             │ normalise
             ▼
   data/candidate.json  ──validate──►  FAIL: stop, latest.json untouched
             │ PASS + approved
             ▼ atomic rename
   data/latest.json ◄──── snapshots/ (rollback source)
             │
             ▼
   ┌────────────────────┐
   │ Digest app (Express)│  in-memory cache, last-known-good fallback
   │ GET / /api/stories  │
   │ GET /api/health     │
   └─────────┬───────────┘
            ▼
       SigNoz (OTLP)  ◄──── pipeline spans, linked by TRACEPARENT env
```

### 4.1 Repository layout

```
zero-downtime-factory/
├── README.md
├── SPEC.md
├── CLAUDE.md
├── .cursor/rules
├── .env.example
├── .gitignore
├── Makefile
├── package.json
├── agent-rules/scraper.md
├── bin/factory
├── src/config.js, logger.js, lock.js, atomic.js, state.js, ids.js
├── src/adapters/brightdata/{index.js,commands.js,exec.js,classify.js}
├── src/adapters/port/{index.js,mcp.js,rest.js,ledger.js}
├── src/pipeline/{normalize.js,validate.js,promote.js,run.js}
├── src/telemetry/{otel.js,context.js,metrics.js}
├── src/commands/{scrape,heal,approve,reject,promote,rollback,status,break,run,port-sync,port-flush,doctor}.js
├── app/{package.json,server.js,instrumentation.js,store.js,public/index.html,public/styles.css}
├── data/{.gitkeep,collectors.md,raw/,snapshots/,sample-output/,candidate.json,latest.json,state.json}
├── port/{brief.md,blueprints.md,blueprints/*.json,workflows.md,state/}
├── observability/{instrumentation.md,dashboard-checklist.md,signoz-dashboard.json}
├── scripts/{setup.sh,probe.sh,scrape.sh,heal.sh,factory-run.sh,demo.sh,reset.sh}
├── tests/{fixtures/,unit/,integration/,chaos/}
└── docs/{cli-surface.md,DEMO_RUNBOOK.md,TROUBLESHOOTING.md}
```

Create ALL of these. candidate.json/latest.json/state.json are gitignored (not committed). Use .gitkeep in raw/snapshots/port/state.

---

## 5. State machine

### `REQ-SM-01` (P0)
`data/state.json` is the only mutable factory status document. Writes go through `atomicWriteJson`. Schema:

```json
{
  "schema_version": 1,
  "status": "UNKNOWN",
  "consecutive_failures": 0,
  "circuit_open": false,
  "collector_id": null,
  "last_run_id": null,
  "last_good_run_id": null,
  "last_error": null,
  "verification_failed": false,
  "approval": {
    "id": null,
    "status": "none",
    "requested_at": null,
    "resolved_at": null
  },
  "updated_at": "1970-01-01T00:00:00.000Z"
}
```

`status` is one of: `UNKNOWN`, `HEALTHY`, `DEGRADED`, `BROKEN`, `HEALING`, `PENDING_APPROVAL`, `RECOVERED`.

`approval.status` is one of: `none`, `pending`, `approved`, `rejected`.

### Legal transitions

| From | To | Trigger |
|:--|:--|:--|
| UNKNOWN | HEALTHY | First successful promote |
| UNKNOWN | DEGRADED | First scrape produced a candidate that failed a soft gate (not used; first hard fail goes BROKEN) |
| UNKNOWN | BROKEN | First scrape or validate fail |
| HEALTHY | HEALTHY | Successful scrape + promote |
| HEALTHY | DEGRADED | `consecutive_failures == 1` after a failed scrape (latest still valid) |
| HEALTHY | BROKEN | Hard classify fail, or `factory break` |
| DEGRADED | HEALTHY | Successful promote |
| DEGRADED | DEGRADED | Another isolated fail while `consecutive_failures < 3` |
| DEGRADED | BROKEN | `consecutive_failures >= 3` or `factory break` |
| BROKEN | HEALING | `factory heal` (DEC-07: never automatic) |
| BROKEN | BROKEN | Failed scrape while already broken |
| HEALING | PENDING_APPROVAL | Heal preview accepted by the adapter |
| HEALING | BROKEN | Heal verification fail (`EC-SM-04`) |
| PENDING_APPROVAL | RECOVERED | `factory approve` |
| PENDING_APPROVAL | BROKEN | `factory reject` |
| PENDING_APPROVAL | HEALING | `factory heal` again |
| RECOVERED | HEALTHY | Successful scrape + promote after approve |
| RECOVERED | BROKEN | Verification re-run fails |
| RECOVERED | DEGRADED | Soft fail after recover |

Same-state writes are allowed (heartbeats, bookkeeping).

### `EC-SM-01` (P0)
Illegal transition: do not write the new status. Exit code `3`. Message names both states.

### `EC-SM-02` (P0)
If `data/state.json` is missing or unreadable: reconstruct.
- Valid `data/latest.json` exists → `HEALTHY`, `consecutive_failures = 0`.
- Otherwise → `UNKNOWN`.

### `EC-SM-03` (P0)
When `consecutive_failures >= 3`, set `circuit_open = true`. `factory scrape` and `factory run` then exit `7` until `factory heal` or `factory reset` (via `make reset` / `scripts/reset.sh`) clears the circuit. `status`, `doctor`, `rollback`, `break` still run.

### `EC-SM-04` (P0)
Heal verification fail (adapter heal classified as failure, or preview JSON unusable): transition `HEALING → BROKEN`, set `verification_failed: true`, exit `9`.

Promotion is blocked while `approval.status` is `pending` or `rejected` or `none` after a heal. Only `approved` opens the gate. Normal HEALTHY/UNKNOWN scrapes do not need an approval record.

---

## 6. Data contracts

### Story

```json
{
  "id": "hn-123",
  "rank": 1,
  "title": "Example",
  "url": "https://example.com",
  "site": "example.com",
  "points": 42,
  "comment_count": 7,
  "author": "pg",
  "age": "3 hours ago",
  "is_job": false
}
```

### `latest.json` envelope

```json
{
  "schema_version": 1,
  "generated_at": "2026-08-22T00:00:00.000Z",
  "source": "https://news.ycombinator.com",
  "collector_id": "c_hn_digest_factory",
  "run_id": "run-...",
  "story_count": 2,
  "stories": []
}
```

### Normalise rules (`src/pipeline/normalize.js`)

| ID | Rule |
|:--|:--|
| N-01 | Unwrap raw: array, or `{stories\|items\|hits\|data\|result\|records}` |
| N-02 | `title` from `title\|headline\|name\|text` |
| N-03 | `url` from `url\|link\|href\|story_url` |
| N-04 | `points` from `points\|score\|points_count`, coerce number, default `0` |
| N-05 | `comment_count` from `comment_count\|comments\|descendants\|num_comments`, coerce number, default `0` |
| N-06 | `author` from `author\|by\|user\|username`, default `""` |
| N-07 | `age` from `age\|time_ago\|created_at`, else `null` |
| N-08 | `id` from `id\|objectID\|story_id`, else stable hash of url+title |
| N-09 | `is_job` when title matches `/hiring\|\bjob\b\|who is hiring\|ask hn/i` or URL is an HN item page with no external link |
| N-10 | Dedupe by url, keep the higher `points` row |
| N-11 | Sort by incoming rank or points desc, assign `rank` 1..n, cap 30 |

### Quality gates (`src/pipeline/validate.js`)

| ID | Gate |
|:--|:--|
| G1 | Document is a plain object |
| G2 | `schema_version === 1` |
| G3 | `generated_at` is valid ISO-8601 |
| G4 | `source` is a non-empty string |
| G5 | `stories` is an array |
| G6 | `stories.length >= 1` |
| G7 | Every story has a non-empty `title` string |
| G8 | Every story has an `http(s)` url, **or** `is_job === true` |
| G9 | `points` and `comment_count` are finite numbers `>= 0` |
| G10 | No duplicate story urls (empty urls ignored) |
| G11 | `collector_id` and `run_id` are non-empty strings |

### `REQ-VAL-01` (P0)
`validate(doc)` is a pure function. No filesystem, no network, no Date.now unless the caller passed the document in. Returns `{ ok, gates, errors }` where `gates` is `{ G1: boolean, ... G11 }` and `errors` is `[{ gate, message }]`.

### `REQ-VAL-02` (P1)
When validation runs inside a span, set attributes `factory.validation.ok` (bool) and `factory.validation.failed_gates` (comma-separated failed gate ids).

### `EC-DATA-01` (P0)
Hacker News job posts ("Who is hiring?", Ask HN jobs) **PASS**. Do not fail G8/G9 because points or an external url are missing. Normalise sets `is_job: true` and `points`/`comment_count` to `0` when absent.

---

## 7. Edge cases

### Files (`EC-FILE-*`)

| ID | Trigger | Behaviour |
|:--|:--|:--|
| EC-FILE-01 | Process crash mid-write | Temp file + `fsync` + `rename`. `latest.json` is the previous valid file or absent. |
| EC-FILE-02 | Missing `data/` dirs | Create them. Do not fail. |
| EC-FILE-03 | Concurrent factory processes | Exclusive lock on `data/.factory.lock`. Second process exits `6`. |
| EC-FILE-04 | Stale lock (pid dead) | Steal the lock. |
| EC-FILE-05 | `latest.json` absent | App serves last-known-good cache or an honest empty-but-alive page. HTTP 200. |
| EC-FILE-06 | Corrupt `latest.json` | App does not throw. Health `degraded`. Body still renders. |

### Bright Data (`EC-BD-*`)

| ID | Trigger | Behaviour |
|:--|:--|:--|
| EC-BD-01 | CLI timeout | Classify `FAIL_TIMEOUT`, do not promote, exit `5`. |
| EC-BD-02 | Banner or progress on stdout | Extract first balanced JSON (`EC-PROBE-03`). |
| EC-BD-03 | `-o` ignored | Fall back to stdout extract. |
| EC-BD-04 | Auth fail | Classify `FAIL_AUTH`, exit `5`. latest untouched. |
| EC-BD-05 | Collector missing | Classify `FAIL_NOT_FOUND`, exit `5`. |
| EC-BD-06 | Unparseable output | Classify `FAIL_PARSE`, exit `10`. |
| EC-BD-07 | Replay mode | Never invoke the real CLI. Read `data/sample-output/`. |

### Data (`EC-DATA-*`)

| ID | Trigger | Behaviour |
|:--|:--|:--|
| EC-DATA-01 | Job posts | PASS (see Section 6). |
| EC-DATA-02 | Empty stories | FAIL G6. latest untouched. |
| EC-DATA-03 | HTML instead of JSON | `FAIL_PARSE`. |
| EC-DATA-04 | Duplicate urls | FAIL G10. |
| EC-DATA-05 | String numbers in raw | Coerce via N-04/N-05. |

### App (`EC-APP-*`)

| ID | Trigger | Behaviour |
|:--|:--|:--|
| EC-APP-01 | Missing latest | 200 + last-known-good or waiting state. Never a stack dump. |
| EC-APP-02 | Corrupt latest | 200 + last-known-good. `/api/health` reports `degraded`. |
| EC-APP-03 | File changes on disk | Next poll / next request reloads. In-memory cache invalidates on mtime. |

### Port (`EC-PORT-*`)

| ID | Trigger | Behaviour |
|:--|:--|:--|
| EC-PORT-01 | Login / network fail | Ledger write succeeds. Remote error logged. Pipeline continues. |
| EC-PORT-02 | Partial remote write | Ledger is source of truth. `factory port-flush` retries. |
| EC-PORT-03 | Missing Port creds | Skip remote. Still ledger. |

### OTEL (`EC-OTEL-*`)

| ID | Trigger | Behaviour |
|:--|:--|:--|
| EC-OTEL-01 | Exporter hang | 3s timeout, swallow, continue. |
| EC-OTEL-02 | Auth / connect fail | Log once per process. Never throw into the pipeline. |
| EC-OTEL-03 | Missing endpoint | No-op tracer. Commands still work. |

### Demo (`EC-DEMO-*`)

| ID | Trigger | Behaviour |
|:--|:--|:--|
| EC-DEMO-01 | `make reset` | Restore replay fixtures, clear lock/broken/state/latest/candidate, keep sample-output. |
| EC-DEMO-02 | Offline venue | `FACTORY_MODE=replay` and `make demo-offline` succeed with no network. |
| EC-DEMO-03 | App up during break | Digest keeps serving last good document. |

---

## 8. CLI

`bin/factory` is a Node ESM executable.

```
factory <command> [options]
```

Commands: `scrape`, `validate`, `heal`, `approve`, `reject`, `promote`, `rollback`, `status`, `break`, `run`, `port-sync`, `port-flush`, `doctor`.

Global flags: `--json`, `--verbose`, `--dry-run`, `--collector-id <id>`, `--url <url>`.

### Exit codes (Appendix A)

| Code | Name | When |
|:--|:--|:--|
| 0 | SUCCESS | Command completed |
| 1 | GENERIC | Unexpected error |
| 2 | CONFIG | Missing/invalid named env or collector id |
| 3 | ILLEGAL_TRANSITION | EC-SM-01 |
| 4 | VALIDATION | Candidate failed gates |
| 5 | SCRAPE | Adapter live/record failure (not parse) |
| 6 | LOCK | Lock held by a live pid |
| 7 | CIRCUIT | Circuit open (EC-SM-03) |
| 8 | NOT_APPROVED | Promote blocked by approval gate |
| 9 | HEAL | Heal failed or verification_failed |
| 10 | PARSE | FAIL_PARSE |
| 11 | FILE | Unexpected filesystem error |
| 12 | USAGE | Unknown command or bad flags |

`--dry-run` prints the planned action and exits 0 without writing `latest.json`.

---

## 9. Observability

### `REQ-OTEL-01`
Service name is always `zero-downtime-factory`. Resource attribute `factory.component` is `app` or `pipeline` (DEC-08).

### Span catalogue

| Span | Component | Notes |
|:--|:--|:--|
| `factory.run` | pipeline | Parent of a full run |
| `factory.scrape` | pipeline | Adapter invocation |
| `factory.normalize` | pipeline | |
| `factory.validate` | pipeline | REQ-VAL-02 attrs |
| `factory.promote` | pipeline | |
| `factory.heal` | pipeline | First-class heal signal |
| `factory.approve` | pipeline | |
| `factory.reject` | pipeline | |
| `factory.rollback` | pipeline | |
| `factory.break` | pipeline | Chaos |
| `factory.port.upsert` | pipeline | |
| `app.request` | app | HTTP |
| `app.store.load` | app | |

### Events
`factory.failure`, `factory.heal.requested`, `factory.heal.pending`, `factory.approved`, `factory.promoted`.

### TRACEPARENT
`src/telemetry/context.js` reads `process.env.TRACEPARENT` (W3C) and continues the trace. Child processes inherit the env var. Demo sets one TRACEPARENT for the whole break→heal→approve→re-run story.

### Export
OTLP/HTTP. Timeout 3000ms. Failures swallowed, logged once (DEC-06, EC-OTEL-01/02).

Dashboard JSON lives at `observability/signoz-dashboard.json` (latency, throughput, errors).

---

## 10. Port

Four entity types. Blueprints in `port/blueprints/`.

| Identifier | Purpose |
|:--|:--|
| `service` | Digest app |
| `scraper` | Bright Data collector |
| `factory_run` | One pipeline run |
| `approval` | Human gate |

`upsertEntity(type, id, props)`:
1. Append to `port/state/ledger.jsonl` (always).
2. Attempt MCP, then REST.
3. Remote failure is recorded on the ledger line and never thrown to the caller (DEC-05).

`factory port-sync` upserts current service/scraper/run/approval.
`factory port-flush` retries ledger lines with `remote_ok: false`.

Workflows documented in `port/workflows.md`. Human approval **blocks promotion**.

---

## 11. Tests

All tests use `node:test` and `node:assert`. `FACTORY_MODE=replay` unless a test is explicitly live (none are in CI).

Fixtures live in `tests/fixtures/`. Verdicts for the 14 validate documents are in `tests/fixtures/verdicts.json`.

| ID | File | Asserts |
|:--|:--|:--|
| TEST-UNIT-01 | `tests/unit/validate.test.js` | All 14 fixtures match `verdicts.json`. Job posts PASS. |
| TEST-UNIT-02 | `tests/unit/normalize.test.js` | N-01..N-11, including string scores and nested hits. |
| TEST-UNIT-03 | `tests/unit/atomic.test.js` | Rename is atomic; a planted tmp file never becomes latest. |
| TEST-UNIT-04 | `tests/unit/lock.test.js` | Second acquire fails; dead pid is stolen. |
| TEST-UNIT-05 | `tests/unit/config.test.js` | Collector ID precedence: flag, env, CLAUDE.md, agent-rules. |
| TEST-UNIT-06 | `tests/unit/state.test.js` | Illegal transition exit 3; reconstruct; circuit at 3 fails. |
| TEST-INT-01 | `tests/integration/happy-path.test.js` | Replay scrape → validate → promote. latest valid. |
| TEST-INT-02 | `tests/integration/failed-scrape.test.js` | Failed scrape leaves latest untouched. |
| TEST-INT-03 | `tests/integration/heal-approve.test.js` | heal → pending → approve → re-run, same collector id. |
| TEST-INT-04 | `tests/integration/port-ledger.test.js` | Remote fail still writes ledger; pipeline exit 0. |
| TEST-INT-05 | `tests/integration/reject-rollback.test.js` | reject blocks promote; rollback restores snapshot. |
| TEST-CHAOS-01 | `tests/chaos/break.test.js` | `factory break` then scrape fails. |
| TEST-CHAOS-02 | `tests/chaos/missing-latest.test.js` | App 200 with no latest.json. |
| TEST-CHAOS-03 | `tests/chaos/otel-down.test.js` | Bad OTLP endpoint, pipeline still succeeds. |
| TEST-CHAOS-04 | `tests/chaos/corrupt-latest.test.js` | Corrupt latest, app 200 + degraded health. |
| TEST-CHAOS-05 | `tests/chaos/replay-offline.test.js` | Replay scrape with PATH that cannot reach the network still works. |
| TEST-APP-01 | `tests/app/html.test.js` | `GET /` is HTML and lists story titles. |
| TEST-APP-02 | `tests/app/api.test.js` | `/api/stories` and `/api/health` JSON. |
| TEST-DEMO-01 | `tests/demo/offline.test.js` | `make demo-offline` (or the demo script in replay) exits 0. |

---

## 12. Config

`.env.example` lists every named variable. Fail-fast messages **name the variable**.

Collector ID precedence (`REQ-CFG-01`):

1. `--collector-id`
2. `FACTORY_COLLECTOR_ID` then `BRIGHTDATA_COLLECTOR_ID`
3. `SCRAPER_STUDIO_COLLECTOR_ID=...` in `CLAUDE.md`
4. Same key in `agent-rules/scraper.md`

`FACTORY_MODE` is `live` | `record` | `replay`. Default `replay`.

Live mode without `BRIGHTDATA_API_KEY` exits `2`.

`FACTORY_ROOT` overrides the repo root (tests only).

---

## 13. Agent rules

`CLAUDE.md` is the operator file. Copy the scraper contract into `.cursor/rules` and `agent-rules/scraper.md`.

Must include:

- `SCRAPER_STUDIO_COLLECTOR_ID=c_hn_digest_factory`
- INV-1
- Heal is triggered, never automatic
- Never write Bright Data output straight to `data/latest.json`
- Reuse the same Collector ID after heal

---

## 14. Implementation phases

| Phase | Deliver | Acceptance |
|:--|:--|:--|
| P0 | Layout, package.jsons, gitignore, env example, docs stubs, fixtures, Port blueprint JSON | `npm test` runs; `git status` shows no secrets |
| P1 | probe.sh, commands.js, config, atomic, lock, state, logger, ids | TEST-UNIT-03, 04, 06 green; `docs/cli-surface.md` has real `--help` |
| P2 | normalize, validate, `factory validate` | All 14 fixtures match verdicts; TEST-UNIT-01, 02 green; jobs PASS |
| P3 | Bright Data adapter, promote, scrape, break, replay | TEST-INT-01, INT-02, CHAOS-01, CHAOS-05 |
| P4 | Express digest | TEST-APP-01, APP-02, CHAOS-02, CHAOS-04 |
| P5 | heal / approve / reject / rollback | TEST-INT-01, INT-03, INT-05 |
| P6 | Port adapters, bootstrap/sync/flush, ledger | TEST-INT-04 |
| P7 | SigNoz, TRACEPARENT, dashboard, `factory doctor` OTEL check | TEST-CHAOS-03 |
| P8 | demo.sh, make reset, make demo-offline, runbooks | TEST-DEMO-01 |
| P9 | README definition of done | Checklist complete |

---

## 15. Makefile

Targets: `setup`, `test`, `probe`, `scrape`, `heal`, `approve`, `demo`, `demo-offline`, `reset`, `app`, `doctor`, `port-sync`.

```
setup:        ./scripts/setup.sh
test:         npm test
probe:        ./scripts/probe.sh
scrape:       ./scripts/scrape.sh
heal:         ./scripts/heal.sh
approve:      ./bin/factory approve
demo:         ./scripts/demo.sh
demo-offline: FACTORY_MODE=replay ./scripts/demo.sh
reset:        ./scripts/reset.sh
app:          node --import ./app/instrumentation.js app/server.js
doctor:       ./bin/factory doctor
port-sync:    ./bin/factory port-sync
```

---

## 16. DEMO_RUNBOOK.md

A timed offline rehearsal: reset → start app → scrape → break → confirm app still serves → heal → confirm promote blocked → approve → re-run → promote → confirm stories refresh. One TRACEPARENT for the whole story.

---

## 17. Definition of done

See README. Every TEST-* green, INV-1 held during `make demo-offline`, Collector ID unchanged across heal, Port ledger populated, SigNoz dashboard JSON present, no secrets in git.

---

## Appendix A. Exit codes

Documented in README and Section 8. Codes 0–12.

## Appendix C. FastAPI variant

Out of scope (DEC-01). Do not implement.
