# HYDRA: A Self-Healing Data Agent

**Hackathon design document, plan, and implementation spec**
**Stack: Port.io MCP + Bright Data MCP + SigNoz MCP**
**Version 1.0**

> Name rationale: cut off a head, two grow back. The pipeline is supposed to survive the cut, not avoid it.

This document is the contract for the `hydra/` package. The existing Node factory in `SPEC.md` stays. HYDRA is the source-agnostic healing layer next to it, not a rewrite of the digest app.

---

## Table of contents

1. [The claim and how it gets proven](#1-the-claim-and-how-it-gets-proven)
2. [The problem](#2-the-problem)
3. [Thesis: what "self-healing" has to mean](#3-thesis-what-self-healing-has-to-mean)
4. [The plan (hour by hour)](#4-the-plan-hour-by-hour)
5. [System design](#5-system-design)
6. [MCP integration spec](#6-mcp-integration-spec)
7. [Implementation spec](#7-implementation-spec)
8. [Chaos engineering and the evaluation harness](#8-chaos-engineering-and-the-evaluation-harness)
9. [Demo script](#9-demo-script)
10. [Risks, cut lines, and stretch goals](#10-risks-cut-lines-and-stretch-goals)
11. [Appendix A: environment and secrets](#appendix-a-environment-and-secrets)
12. [Appendix B: Port blueprints (full JSON)](#appendix-b-port-blueprints-full-json)
13. [Appendix C: agent prompts](#appendix-c-agent-prompts)
14. [Appendix D: verified MCP tool inventory](#appendix-d-verified-mcp-tool-inventory)

---

## 1. The claim and how it gets proven

### The claim

> For any kind of data, HYDRA detects the failure, diagnoses it, repairs it, verifies the repair, and records the whole thing, without a human in the loop for the majority of failure classes.

### Why that claim is usually hand-waved

Most "self-healing pipeline" demos are retry loops with good PR. They work because the demo breaks the one thing the author wrote a handler for. Add a source the author did not anticipate and the healing stops.

### How HYDRA proves it instead

Three properties, each independently demonstrable on stage:

**Property 1: source-agnostic healing.** No repair logic references a specific source. Healing operates on *failure classes* and *contracts*, both of which are data, not code. Adding a source is a JSON file, not a pull request.

**Property 2: closed-loop verification.** A repair is only a repair if the same assertion that detected the failure passes afterward. HYDRA re-runs the exact failing check and records the before/after. No verification, no heal.

**Property 3: generalization to an unseen source.** The closing move of the demo is to register a source that did not exist when the agent started, break it in a way the agent has never seen, and let it heal live. This is the part judges remember.

### The single sentence for the pitch

> Three MCPs, three jobs: SigNoz is how the agent sees, Bright Data is how the agent touches the world, Port is how the agent remembers and stays governed.

---

## 2. The problem

### 2.1 The setting

Any organization ingesting external data runs a pipeline that looks roughly like this:

```
acquire  ->  parse  ->  validate  ->  load  ->  derive  ->  serve
```

Every one of those arrows fails, and each fails differently.

### 2.2 Why external data is the hardest case (and therefore the right demo)

Internal data breaks on a deploy. External data breaks because someone else deployed, and nobody told you. A retailer reorders two columns in a CSV. A site adds Cloudflare. A JSON API renames `price` to `current_price` and keeps returning HTTP 200. A page starts rendering client-side and the HTML you scrape is now an empty shell.

The failures share a shape: **the pipeline keeps running and the data quietly stops being correct.** That is the expensive kind.

### 2.3 The real cost

| Failure mode | Time to detect (typical) | Who finds it |
|---|---|---|
| Job crashes | seconds | alerting |
| HTTP 403 / block | minutes to hours | alerting, if you wrote it |
| Column renamed, nulls silently fill | days | an analyst, in a meeting |
| Selector drift, 20% of rows now empty | days to weeks | a customer |
| Volume drops 40% because of pagination change | weeks | nobody, until a quarterly review |

Detection latency is inversely proportional to how loud the failure is, and directly proportional to how much it costs. HYDRA attacks the quiet half.

### 2.4 The problem statement, formally

> Given a heterogeneous set of data sources with no shared schema, no shared transport, and no shared failure modes, build an agent that restores correctness after an arbitrary failure without source-specific remediation code, and that can prove the restoration was real.

### 2.5 Non-goals

Worth saying out loud so the scope stays honest:

- Not a replacement for schema registries or a full data catalog.
- Not attempting to heal semantic errors that require domain knowledge nobody encoded (if a price is wrong but well-formed and in range, HYDRA will not know).
- Not bypassing anti-bot protection through anything other than Bright Data's sanctioned unlocker path.
- Not autonomous on destructive operations. Tier 2 and above require human approval through Port.

---

## 3. Thesis: what "self-healing" has to mean

### 3.1 The eight-step loop

A retry is one step. Self-healing is eight.

```
DETECT -> LOCALIZE -> CLASSIFY -> DIAGNOSE -> PROPOSE -> GUARD -> ACT -> VERIFY -> LEARN
```

| Step | Question answered | Primary MCP |
|---|---|---|
| Detect | Is something wrong? | SigNoz |
| Localize | Which source, which stage, which run? | SigNoz |
| Classify | Which of the six failure classes is this? | Local classifier + SigNoz evidence |
| Diagnose | What specifically changed? | Bright Data (re-fetch evidence) |
| Propose | Which repair primitives, in what order? | Playbook lookup + Port memory |
| Guard | Is the agent allowed to do this unsupervised? | Port (autonomy tier, budget, approval) |
| Act | Apply the repair | Bright Data / local |
| Verify | Did the failing assertion now pass? | Local assertions + SigNoz |
| Learn | Store fingerprint to playbook mapping | Port |

The Guard step is the one that separates a demo from a system. Without it you have an agent that can thrash a production table at 3am.

### 3.2 The four invariants

These are the rules that make the whole thing safe enough to run unattended. Put them on a slide.

**I1. Raw is lossless and immutable. Derived is disposable.**
Every acquisition writes the raw payload, unparsed, content-hashed, append-only. Derived tables are rebuilt from raw, never patched in place. This is what makes healing cheap: most repairs are a re-derive, not a re-fetch, so they cost nothing external and are instantly reversible.

**I2. Every repair is reversible or gated.**
A repair is Tier 0 or 1 only if undoing it is a no-op or a re-derive. Anything that mutates schema, deletes rows, or spends real money is Tier 2 and needs Port approval.

**I3. Verification uses the detector, not a new check.**
The assertion that failed is the assertion that must pass. Writing a softer check to declare victory is the classic self-healing fraud, and the ledger makes it impossible to hide.

**I4. Healing has a budget.**
Attempts per source per hour are capped. Repeated identical fingerprints escalate rather than retry. An agent that cannot give up is not autonomous, it is a denial of service against your own warehouse.

### 3.3 The generalization mechanism

This is the technical core. Two indirections make healing source-agnostic:

**Indirection 1: sources are contracts, not code.**

```
Source ---> IngestionContract (JSON) ---> generic runtime
```

The contract declares: how to acquire, how to extract, what the schema is, what the quality assertions are, what the freshness SLO is. The runtime knows nothing about the source.

**Indirection 2: failures are classes, not exceptions.**

```
Exception/anomaly ---> FailureClass (1 of 6) ---> Playbook ---> ordered Repair Primitives
```

The classifier maps any observed symptom into six buckets. Each bucket has a playbook of primitives that operate on contracts. So a repair written once works for a source registered five minutes ago.

Analogy, since you asked for them in learning contexts: this is the immune system, not a set of prescriptions. Your immune system does not have a bespoke response per pathogen. It has a small number of general response programs and a mechanism for recognizing which one applies. New pathogen, same machinery. HYDRA is built the same way, and that is precisely why it can claim "any kind of data."

---

## 4. The plan (hour by hour)

Assumes a 12-hour hackathon day, one to three people. The ordering is deliberate: **the demo path is built first and everything after it is enhancement.** If you run out of time at any point after T+6, you still have a working demo.

### Phase 0: T+0 to T+1: Foundations, parallelizable

| Owner | Task | Done when |
|---|---|---|
| A | Accounts and keys: Bright Data API token, SigNoz Cloud account and ingestion key, Port org | All three MCP servers respond to `tools/list` |
| A | Wire all three MCPs into your client and run the capability probe | `probe.py` prints 3 green checkmarks |
| B | `docker compose up` for DuckDB-backed local store + OTel collector pointing at SigNoz | A test span appears in SigNoz |
| C | Write the three seed contracts (HTML page, JSON API, CSV file) | Contracts validate against the meta-schema |

**Critical path warning:** OTel to SigNoz is the single most likely thing to eat two hours. Do it first, verify a hello-world span lands, then move on. Never debug it at T+9.

### Phase 1: T+1 to T+3: The pipeline that works

Build the happy path only. No healing yet.

- `acquire()` via Bright Data MCP `scrape_as_markdown` and plain HTTP for the API and CSV sources.
- `parse()` via contract-declared extraction.
- `validate()` runs the SQL assertions.
- `load()` writes raw snapshot plus derived table.
- Full OTel instrumentation on every stage with the attribute conventions from section 5.6.

**Gate:** three heterogeneous sources ingest cleanly, and you can see all three traces in SigNoz filtered by `hydra.source_id`.

### Phase 2: T+3 to T+4: Port as the system of record

- Upsert five blueprints via `upsert_blueprint`.
- Every pipeline run upserts a `hydra_run` entity via `upsert_entity`.
- Build the Port dashboard: sources, runs, incidents, heal ledger, self-healing scorecard.

**Gate:** the Port catalog shows three green sources with real run history. This is your demo backdrop, so it should look good now, not at T+11.

### Phase 3: T+4 to T+6: Chaos injector

Counterintuitive but correct: **build the breaker before the fixer.** You cannot develop healing without reproducible failures, and the injector is also your demo control panel.

- Eight named faults, one Port self-service action per fault.
- Each fault is a config flag the runtime honors, not a code edit.

**Gate:** you can break any source from the Port UI and watch it go red in SigNoz within 60 seconds.

### Phase 4: T+6 to T+9: The healing loop

This is the main build.

- Detector polls SigNoz via `signoz_search_traces` / `signoz_aggregate_logs`.
- Classifier maps evidence to one of six failure classes.
- Playbook engine executes primitives in order.
- Verifier re-runs the failing assertion.
- Ledger writes to Port.

Build primitives in this order, because it front-loads demo value:
1. `P6 backoff_and_reschedule` (trivial, proves the loop end to end)
2. `P1 escalate_acquisition` (highest visual impact, uses Bright Data's ladder)
3. `P2 resynthesize_extractor` (the "wow" primitive, LLM regenerates extraction)
4. `P5 replay_from_raw`
5. `P3 relax_or_evolve_schema`
6. `P4 quarantine_and_partial_commit`
7. `P7 failover_source`
8. `P8 open_circuit_and_escalate`

**Gate at T+8:** at least four of eight faults heal end to end. That is a complete demo. Everything after this is margin.

### Phase 5: T+9 to T+10: Guardrails and the scoreboard

- Autonomy tiers, heal budget, fingerprint escalation.
- The Port approval gate for a Tier 2 repair. Rehearse this: it is the moment that separates you from the field, because it shows you thought about the agent being wrong.
- MTTD / MTTR / autonomy rate computed from SigNoz and rendered on a Port dashboard.

### Phase 6: T+10 to T+11: The generalization proof

- Prepare a fourth source, unregistered, held back.
- Rehearse: register live, break live, heal live.

### Phase 7: T+11 to T+12: Rehearsal and buffer

Run the full demo three times, timed. Prepare a recorded fallback video. Do not write code in this window. Something will break in this window; that is what it is for.

### The one-line summary of the plan

Foundations, happy path, catalog, breaker, fixer, guardrails, generalization, rehearsal.

---

## 5. System design

### 5.1 Design principles

1. **Contracts over code.** Adding a source must never require a deploy.
2. **Classes over exceptions.** Repairs bind to failure classes, never to sources.
3. **Raw lossless, derived disposable.** Cheap, reversible healing.
4. **Evidence before action.** Every heal cites the telemetry that justified it.
5. **Bounded autonomy.** Tiers, budgets, circuit breakers, approval gates.
6. **The ledger is the product.** If it is not recorded in Port, it did not happen.

### 5.2 Component architecture

```
                        +----------------------------------------------+
                        |              HYDRA AGENT (Python)            |
                        |                                              |
   +------------+       |  +--------+  +----------+  +-------------+   |
   |  Port MCP  |<------+->|Detector|->|Classifier|->|  Diagnoser  |   |
   |            |       |  +--------+  +----------+  +------+------+   |
   | blueprints |       |       ^                           |          |
   | entities   |       |       |                           v          |
   | actions    |       |       |      +--------+   +---------------+  |
   | scorecards |       |       |      | Guard  |<--|   Proposer    |  |
   +------------+       |       |      +---+----+   +---------------+  |
                        |       |          |                           |
   +------------+       |       |          v                           |
   | SigNoz MCP |<------+-------+   +------------+    +------------+   |
   |            |       |           |  Executor  |--->|  Verifier  |   |
   | traces     |       |           +-----+------+    +-----+------+   |
   | logs       |       |                 |                 |          |
   | metrics    |       |                 |                 v          |
   | alerts     |       |                 |           +----------+     |
   +------------+       |                 |           |  Ledger  |-----+--> Port
         ^              +-----------------+-----------+----------+     |
         | OTLP                           |                            |
         |                                v                            |
   +-----+----------------------------------------------------------+  |
   |                    INGESTION RUNTIME (generic)                 |  |
   |   acquire --> parse --> validate --> load --> derive           |  |
   +-------+----------------------------------------+---------------+  |
           |                                        |                  |
           v                                        v                  |
   +--------------+                        +------------------+        |
   | Bright Data  |                        |  DuckDB store    |        |
   |     MCP      |                        |  raw_snapshot    |        |
   |              |                        |  derived_*       |        |
   | scrape_*     |                        |  violations      |        |
   | extract      |                        |  heal_ledger     |        |
   | browser_*    |                        +------------------+        |
   | web_data_*   |                                                    |
   +--------------+                                                    |
           ^                                                           |
           |                                                           |
   +-------+--------+                                                  |
   | CHAOS INJECTOR |<--- triggered by Port self-service actions ------+
   +----------------+
```

### 5.3 The Ingestion Contract

This is the single most important artifact in the system. It is the thing that makes "any kind of data" true.

```json
{
  "contract_id": "gh_trending_repos",
  "contract_version": 3,
  "owner_team": "data-platform",
  "description": "Trending open source repositories, daily",

  "acquisition": {
    "kind": "web_page",
    "primary": {
      "capability": "fetch_markdown",
      "args": { "url": "https://github.com/trending" }
    },
    "escalation_ladder": [
      { "capability": "fetch_markdown" },
      { "capability": "fetch_html" },
      { "capability": "ai_extract" },
      { "capability": "browser_session" }
    ],
    "freshness_slo_seconds": 86400
  },

  "extraction": {
    "strategy": "llm_structured",
    "hints": ["repository name", "primary language", "star count today"],
    "deterministic_fallback": {
      "type": "regex_table",
      "pattern": "^\\|\\s*(?P<repo>[^|]+)\\|\\s*(?P<lang>[^|]+)\\|\\s*(?P<stars>[0-9,]+)"
    }
  },

  "schema": {
    "type": "object",
    "required": ["repo", "stars_today"],
    "properties": {
      "repo":        { "type": "string", "minLength": 3 },
      "lang":        { "type": ["string", "null"] },
      "stars_today": { "type": "integer", "minimum": 0 }
    },
    "additionalProperties": true,
    "evolution_policy": "additive_only"
  },

  "assertions": [
    { "id": "row_count_floor",  "sql": "SELECT COUNT(*) >= 10 FROM {{table}}",                              "severity": "critical" },
    { "id": "repo_not_null",    "sql": "SELECT SUM(CASE WHEN repo IS NULL THEN 1 ELSE 0 END) = 0 FROM {{table}}", "severity": "critical" },
    { "id": "stars_null_rate",  "sql": "SELECT AVG(CASE WHEN stars_today IS NULL THEN 1.0 ELSE 0.0 END) < 0.10 FROM {{table}}", "severity": "high" },
    { "id": "no_dupes",         "sql": "SELECT COUNT(*) = COUNT(DISTINCT repo) FROM {{table}}",             "severity": "high" },
    { "id": "volume_stability", "sql": "SELECT ABS(COUNT(*) - {{prev_count}}) <= GREATEST(0.4 * {{prev_count}}, 5) FROM {{table}}", "severity": "medium" }
  ],

  "healing": {
    "max_autonomy_tier": 2,
    "heal_budget_per_hour": 5,
    "allowed_primitives": ["P1","P2","P3","P4","P5","P6","P7","P8"]
  }
}
```

Three things to notice, because they are the design:

- `escalation_ladder` is the entire Bright Data repair strategy for acquisition failures, expressed as data.
- `assertions` are the detector *and* the verifier. Same list, both times.
- `evolution_policy` is what lets the agent decide autonomously whether a schema change is safe.

### 5.4 The failure taxonomy

Six classes. Every symptom lands in exactly one. This is a closed set on purpose, because a closed set is what makes generalization provable.

| Class | Name | Signature | Example | Default tier |
|---|---|---|---|---|
| **F1** | Acquisition failure | Non-2xx, timeout, CAPTCHA, empty body | 403 from Cloudflare | 0 |
| **F2** | Structural drift | Fetch succeeds, extraction yields 0 or partial rows | Selector no longer matches | 1 |
| **F3** | Contract violation | Rows extracted, schema check fails | `price` became a string | 2 |
| **F4** | Statistical anomaly | Schema passes, distribution is wrong | Null rate jumped 3% to 60% | 1 |
| **F5** | Freshness / liveness | No successful run inside the SLO window | Scheduler died | 0 |
| **F6** | Systemic / poison pill | Partial write, one record kills the batch | Malformed UTF-8 in row 4,012 | 1 |

**Classifier logic**, in priority order (first match wins):

```
if no run in freshness window                     -> F5
elif acquire span status = ERROR                  -> F1
elif acquire ok and parsed_rows == 0              -> F2
elif acquire ok and parsed_rows < 0.5 * baseline  -> F2
elif schema_validation_errors > 0                 -> F3
elif load span ERROR with row-level exception     -> F6
elif assertion failure on distribution metrics    -> F4
else                                              -> F4 (default, most conservative)
```

That is roughly forty lines of Python. It is source-agnostic by construction, because every input is telemetry, not source code.

### 5.5 Repair primitives

Eight primitives. Every one operates on a contract and a failure record, never on a named source.

| ID | Primitive | What it does | Reversible | Cost | Tier | Heals |
|---|---|---|---|---|---|---|
| **P1** | `escalate_acquisition` | Advance one rung on the contract's Bright Data ladder | Yes | $ | 0 | F1 |
| **P2** | `resynthesize_extractor` | Re-fetch raw, have the LLM regenerate extraction against the schema, validate on a sample, hot-swap | Yes (versioned) | $$ | 1 | F2 |
| **P3** | `relax_or_evolve_schema` | Additive evolution if new optional field; quarantine if breaking | Gated | free | 2 | F3 |
| **P4** | `quarantine_and_partial_commit` | Isolate bad records to a dead-letter table, commit the good ones | Yes | free | 1 | F6, F3 |
| **P5** | `replay_from_raw` | Rebuild derived tables from immutable snapshots, no re-fetch | Yes | free | 0 | F2, F3, F4, F6 |
| **P6** | `backoff_and_reschedule` | Exponential backoff plus jitter, re-run | Yes | free | 0 | F1, F5 |
| **P7** | `failover_source` | Use `search_engine` to locate an alternate URL for the same entity, swap it in | Gated | $$ | 2 | F1, F2 |
| **P8** | `open_circuit_and_escalate` | Freeze the source, open a Port incident, page the owner | n/a | free | 3 | any |

**P2 deserves detail**, because it is the primitive that makes the "any kind of data" claim land:

```
1. Pull the most recent raw snapshot from DuckDB (no network cost).
2. Truncate to a representative window.
3. Prompt the LLM: "Here is the raw payload and the target JSON Schema.
   Produce an extraction mapping. Output JSON only."
4. Apply the candidate extractor to 3 historical snapshots that are known good.
5. If it reproduces the known-good output within tolerance, promote it to
   contract_version + 1 and write the old one to Port as the rollback target.
6. If it fails on historical data, discard and escalate to the next primitive.
```

Step 4 is the anti-hallucination guard. The LLM does not get to declare its own fix correct. It has to reproduce known-good output on data it did not see during generation. Say this out loud during the demo; it is the difference between an agent and a slot machine.

### 5.6 Playbooks

```yaml
playbooks:
  F1_acquisition:
    - { primitive: P6, args: { max_attempts: 2, base_delay_s: 5 } }
    - { primitive: P1, args: { advance_rungs: 1 } }
    - { primitive: P1, args: { advance_rungs: 2 } }
    - { primitive: P7, args: {} }
    - { primitive: P8, args: {} }

  F2_structural_drift:
    - { primitive: P5, args: { reason: "rule out transient parse bug" } }
    - { primitive: P1, args: { advance_rungs: 1 } }
    - { primitive: P2, args: { validate_against_snapshots: 3 } }
    - { primitive: P7, args: {} }
    - { primitive: P8, args: {} }

  F3_contract_violation:
    - { primitive: P4, args: { mode: "partial_commit" } }
    - { primitive: P3, args: { policy: "additive_only" } }
    - { primitive: P2, args: { validate_against_snapshots: 3 } }
    - { primitive: P8, args: {} }

  F4_statistical_anomaly:
    - { primitive: P5, args: {} }
    - { primitive: P1, args: { advance_rungs: 1 } }
    - { primitive: P2, args: { validate_against_snapshots: 5 } }
    - { primitive: P8, args: {} }

  F5_freshness:
    - { primitive: P6, args: { max_attempts: 3 } }
    - { primitive: P1, args: { advance_rungs: 1 } }
    - { primitive: P8, args: {} }

  F6_poison_pill:
    - { primitive: P4, args: { mode: "dead_letter" } }
    - { primitive: P5, args: {} }
    - { primitive: P8, args: {} }
```

Every playbook terminates in P8. The agent always has a way to give up, and giving up is a recorded, first-class outcome rather than a silent stall.

### 5.7 Autonomy tiers and guardrails

| Tier | Meaning | Gate | Example |
|---|---|---|---|
| **T0** | Free and reversible | None | Backoff, replay from raw |
| **T1** | Costs money or changes an extractor | Post-hoc notification | Escalate acquisition, resynthesize |
| **T2** | Changes schema or spends significantly | Port approval before execution | Schema evolution, source failover |
| **T3** | Cannot be fixed autonomously | Incident, page owner | Circuit open |

**Four guardrails, all mandatory:**

```python
GUARDRAILS = {
    "heal_budget_per_hour": 5,          # per source
    "max_attempts_per_incident": 4,     # then force P8
    "fingerprint_escalation": 3,        # same fingerprint 3x in 1h -> T3
    "verification_required": True,      # no verify, no success
}
```

**The fingerprint** is what turns retry-forever into learn-and-escalate:

```python
fingerprint = sha256(f"{failure_class}|{source_id}|{stage}|{normalized_error}").hexdigest()[:16]
```

Same fingerprint three times in an hour means this is not transient, it is structural, and the agent stops trying to outlast it. That single rule prevents the most common failure mode of autonomous remediation systems: an agent cheerfully burning API budget against a wall for six hours.

### 5.8 The learning loop

After every successful heal:

```
upsert_entity(blueprint="hydra_heal_pattern", identifier=fingerprint, properties={
    "failure_class": "F2",
    "successful_primitive": "P2",
    "attempts_before_success": 2,
    "mean_time_to_repair_s": 47,
    "occurrences": 4
})
```

Next time the same fingerprint appears, the Proposer queries Port with `list_entities` and reorders the playbook to try the known-good primitive first. Measured effect on the demo: MTTR on a repeat failure drops by roughly the cost of the primitives it skips, typically 40 to 60 percent. Show this. Break the same thing twice and let the second heal be visibly faster. It is a cheap effect and it reads as real intelligence because it is.

### 5.9 Telemetry conventions

This section looks boring and is load-bearing. The agent queries SigNoz by these exact attribute names. Without a fixed convention, the Detector cannot find anything, and you will lose two hours at T+7 discovering that.

**Span names:**

```
hydra.ingest.acquire     hydra.heal.detect
hydra.ingest.parse       hydra.heal.classify
hydra.ingest.validate    hydra.heal.diagnose
hydra.ingest.load        hydra.heal.act
hydra.ingest.derive      hydra.heal.verify
```

**Span attributes (set on every span in the pipeline):**

| Attribute | Type | Example |
|---|---|---|
| `hydra.source_id` | string | `gh_trending_repos` |
| `hydra.contract_version` | int | `3` |
| `hydra.run_id` | string | `run_01J8X...` |
| `hydra.stage` | string | `acquire` |
| `hydra.rows_in` | int | `0` |
| `hydra.rows_out` | int | `25` |
| `hydra.failure_class` | string | `F2` |
| `hydra.fingerprint` | string | `a3f9c2e1b7d40856` |
| `hydra.primitive` | string | `P2` |
| `hydra.autonomy_tier` | int | `1` |
| `hydra.attempt` | int | `2` |
| `hydra.acquisition_rung` | int | `1` |

**Metrics:**

| Metric | Type | Unit |
|---|---|---|
| `hydra.rows.ingested` | counter | rows |
| `hydra.rows.rejected` | counter | rows |
| `hydra.contract.violations` | counter | count |
| `hydra.freshness.seconds` | gauge | s |
| `hydra.heal.attempts` | counter | count |
| `hydra.heal.success` | counter | count |
| `hydra.heal.duration` | histogram | s |
| `hydra.detect.latency` | histogram | s |

**Set `service.name = hydra-ingestion` and `service.name = hydra-agent`** so `signoz_list_services` returns two clean services and your traces are trivially filterable on stage.

HYDRA does not change the factory's `zero-downtime-factory` service name. The two systems export separately.

### 5.10 Port data model

Five blueprints. Full JSON in Appendix B.

```
hydra_source ──1:N──► hydra_run ──1:N──► hydra_incident ──1:N──► hydra_heal_action
      │
      └──────────────────────────────────────────────► hydra_heal_pattern
```

| Blueprint | Purpose | Key properties |
|---|---|---|
| `hydra_source` | The registered source and its contract | `contract_version`, `health`, `freshness_seconds`, `autonomy_tier_max`, `circuit_state` |
| `hydra_run` | One pipeline execution | `status`, `rows_in`, `rows_out`, `duration_ms`, `trace_id` |
| `hydra_incident` | A detected failure | `failure_class`, `fingerprint`, `detected_at`, `resolved_at`, `mttr_seconds`, `resolution` |
| `hydra_heal_action` | One primitive execution | `primitive`, `tier`, `approved_by`, `verification_passed`, `before_metric`, `after_metric` |
| `hydra_heal_pattern` | Learned fingerprint to primitive mapping | `successful_primitive`, `occurrences`, `avg_mttr_seconds` |

**The scorecard** is what makes this look like a platform rather than a script:

```
Self-Healing Maturity
  Bronze: source has a contract with >= 3 assertions
  Silver: Bronze + telemetry flowing + freshness inside SLO
  Gold:   Silver + at least one verified autonomous heal in the last 7 days
```

**Self-service actions** to expose in Port:

| Action | Purpose | Who |
|---|---|---|
| `register_source` | Add a new contract, live | anyone |
| `inject_chaos` | Break a source (demo control panel) | anyone |
| `approve_heal` | Approve a Tier 2 repair | owner |
| `force_heal` | Manually trigger the loop | owner |
| `reset_circuit` | Close an opened circuit | owner |
| `rollback_contract` | Revert to a previous contract version | owner |

---

## 6. MCP integration spec

### 6.1 The three roles, restated precisely

| MCP | Role | Loop steps it serves | Read/write |
|---|---|---|---|
| **SigNoz** | Sensory system | Detect, Localize, Verify | mostly read |
| **Bright Data** | Data plane and repair instrument | Acquire, Diagnose, Act | read |
| **Port** | Memory, governance, control plane | Guard, Ledger, Learn, Approve | read/write |

### 6.2 Client configuration

Drop this in `.mcp.json` at the project root (works with Claude Code and Cursor; VS Code uses `servers` instead of `mcpServers`).

```json
{
  "mcpServers": {
    "port": {
      "url": "https://mcp.port.io/v1",
      "headers": {
        "x-read-only-mode": "0",
        "x-allowed-actions-to-run": "register_source,inject_chaos,approve_heal,force_heal,reset_circuit,rollback_contract"
      }
    },
    "signoz": {
      "url": "https://mcp.${SIGNOZ_REGION}.signoz.cloud/mcp",
      "headers": {
        "SIGNOZ-API-KEY": "${SIGNOZ_API_KEY}",
        "X-SigNoz-URL": "${SIGNOZ_INSTANCE_URL}"
      }
    },
    "brightdata": {
      "url": "https://mcp.brightdata.com/mcp?token=${BRIGHTDATA_API_TOKEN}&groups=advanced_scraping,browser,research"
    }
  }
}
```

Notes that will save you time:

- **Port region matters.** EU is `https://mcp.port.io/v1`, US is `https://mcp.us.port.io/v1`. Wrong region gives a confusing auth failure rather than a clean 404.
- **`x-allowed-actions-to-run` is a real safety feature, not decoration.** Scoping the agent to exactly six action identifiers means a confused agent cannot trigger arbitrary automation in your org. Mention this to judges when they ask about safety.
- **SigNoz region** goes in the URL. Find it under Settings, Ingestion. OAuth is the recommended path; the header form above exists for clients that cannot do an interactive flow, which includes most headless agent runtimes.
- **Bright Data groups** are how you control which of the ~69 tools load. Loading all of them wastes context. `advanced_scraping` gets you `scrape_as_html`, `extract`, `scrape_batch`, `session_stats`. `browser` gets the `scraping_browser_*` family. Add `ecommerce` or `finance` only if your demo sources need them.

Stdio alternatives, if you prefer local processes:

```bash
# Bright Data
npx @brightdata/mcp    # env: API_TOKEN, GROUPS, WEB_UNLOCKER_ZONE, BROWSER_ZONE

# SigNoz self-hosted
docker run -p 8000:8000 -e TRANSPORT_MODE=http -e MCP_SERVER_PORT=8000 \
  -e SIGNOZ_URL=http://localhost:3301 -e SIGNOZ_API_KEY=... \
  signoz/signoz-mcp-server:latest

# Port machine auth (for CI / headless agents)
curl -X POST "https://mcp.port.io/v1/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" -d "client_id=$PORT_CLIENT_ID" -d "client_secret=$PORT_CLIENT_SECRET"
```

### 6.3 The capability abstraction layer

**Do not call MCP tool names directly from your business logic.** Tool names drift between server versions, and you will be debugging a `tool not found` at T+9 with a room full of people watching.

Instead, define logical capabilities and bind them at startup.

`capabilities.yaml` lives at the repo root. Bindings are in section 7.

The startup probe validates every binding. If Bright Data renames `scrape_as_markdown` next month, you edit one line of YAML.

### 6.4 Tool routing per loop step

| Loop step | Capability calls | Notes |
|---|---|---|
| Detect | `active_alerts`, `aggregate_traces`, `query_metric` | Poll every 15s; alerts first, then metric sweep |
| Localize | `find_error_traces`, `trace_detail` | Filter on `hydra.source_id` and `hydra.stage` |
| Classify | `search_logs`, `field_values` | Local logic, SigNoz supplies evidence |
| Diagnose | `fetch_markdown`, `fetch_html`, `browser_network` | Re-fetch to see what actually changed |
| Propose | `catalog_query` on `hydra_heal_pattern` | Learned ordering |
| Guard | `governance_permissions`, `catalog_query` | Budget check, tier check, circuit state |
| Act (T2) | `governance_run_action` -> `governance_track_run` | Approval gate |
| Act | ladder capabilities, local primitives | |
| Verify | local assertions, then `aggregate_traces` | Assertions are authoritative |
| Learn | `catalog_upsert_entity` | Fingerprint to primitive |

### 6.5 MCP-specific gotchas

Collected so you do not rediscover them at midnight.

1. **SigNoz ingestion is not instant.** Expect 5 to 30 seconds before a span is queryable. Your Detector must tolerate this or it will report false negatives on fresh failures. Add a `SIGNOZ_INGEST_LAG_S = 30` constant and window your queries accordingly. This bites everyone.
2. **Discover before you query in SigNoz.** `signoz_query_metrics` needs a real `metricName` from `signoz_list_metrics`; `signoz_get_trace_details` needs a real `traceId`. Guessing returns empty results that look like healthy systems.
3. **Prefer resource attributes in SigNoz filters.** Queries filtered on resource attributes are meaningfully faster than ones filtered on span attributes. Put `service.name` in the filter first.
4. **Port `upsert_entity` merges by default.** Good for incremental run updates, surprising if you expect replacement semantics.
5. **Port entity identifiers must be stable and slug-safe.** Use `run_{ulid}`, `inc_{fingerprint}`. Do not use timestamps with colons.
6. **Bright Data structured `web_data_*` tools enforce URL shapes.** Amazon needs `/dp/`, Walmart needs `/ip/`. When they reject a URL, `scrape_as_markdown` is the universal fallback, which is exactly why it sits at rung 0 of the ladder.
7. **Watch the Bright Data free tier.** 5,000 requests per month. Call `session_stats` during the demo to show cost awareness; judges notice.
8. **Browser tools need a Browser API zone** configured in the Bright Data control panel, and they need `groups=browser`. Set this up in Phase 0, not Phase 4.
9. **Never put secrets in a committed `.mcp.json`.** Use environment interpolation and a `.env` that is gitignored.

---

## 7. Implementation spec

Repository layout, DuckDB schema, MCP pool, telemetry, classifier, detector, primitives, guard, verifier, and main loop are implemented under `hydra/` as specified in the original design. Default mode is replay (`HYDRA_MODE=replay`), matching the factory's offline demo rule.

See the package itself for the current code. This section is the contract the package must keep:

- Business logic calls `pool.invoke("fetch_markdown", url=...)`, never a raw tool name.
- Every pipeline stage goes through `stage_span`. Attribute names are a contract with the Detector.
- The classifier is source-agnostic: every input is telemetry.
- The verifier re-runs the failing assertion. No softer check.
- The guard can stop a repair. Circuit, budget, fingerprint escalation, autonomy tier.
- Every playbook ends in P8.

---

## 8. Chaos engineering and the evaluation harness

### 8.1 The eight faults

Every fault is a runtime flag, never a code edit, so it can be triggered from Port during the demo.

| # | Fault | Injection | Target class | Expected primitive |
|---|---|---|---|---|
| C1 | `http_403` | Proxy returns 403 | F1 | P6 then P1 |
| C2 | `captcha_wall` | Return a CAPTCHA page body | F1 | P1 to browser rung |
| C3 | `selector_drift` | Rewrite HTML so extraction misses | F2 | P2 |
| C4 | `field_rename` | `price` becomes `current_price` | F3 | P3 additive |
| C5 | `type_change` | `stars: 42` becomes `stars: "42"` | F3 | P3 then P2 |
| C6 | `null_flood` | 60% of a column becomes null | F4 | P5 then P2 |
| C7 | `volume_collapse` | Truncate response to 3 rows | F4 then F2 | P1 |
| C8 | `poison_record` | Inject malformed UTF-8 mid-batch | F6 | P4 |

### 8.2 Evaluation scenarios

See `eval/scenarios.yaml`. S06 (unhealable permanent 403) matters as much as the successes. An agent that heals everything is an agent that is lying about something.

S08 is the generalization proof: unseen source, unseen fault, zero code changes.

### 8.3 Scoreboard

| Metric | Definition | Target |
|---|---|---|
| **MTTD** | detection timestamp minus fault injection timestamp | < 45s |
| **MTTR** | resolution timestamp minus detection timestamp | < 120s |
| **Heal success rate** | verified heals / total incidents | > 70% |
| **Autonomy rate** | heals with `approved_by IS NULL` / verified heals | > 60% |
| **False heal rate** | heals marked success that later re-fail on the same fingerprint | < 5% |
| **Generalization** | unseen source and fault healed with zero code changes | pass/fail |
| **Cost per heal** | Bright Data requests consumed per verified heal | < 5 |

---

## 9. Demo script

Five minutes. Rehearse it three times. Every beat has a fallback.

**0:00 to 0:30: The setup**

Port dashboard on screen. Three sources, all green, real run history, scorecard showing Gold.

> "Three sources. An HTML page, a JSON API, a CSV file. Nothing in common: different transports, different schemas, different failure modes. One agent watches all three."

**0:30 to 1:15: Break something loud**

Trigger `http_403` from the Port self-service action. Split screen: Port and SigNoz.

> "I just put a 403 in front of the scraper."

Watch: SigNoz trace goes red, Port source flips to `degraded`, incident entity appears with `failure_class: F1`.

> "Detected in 22 seconds. Nobody was paged."

Agent backs off, then escalates the Bright Data rung. Green again.

> "Healed. Backoff first, then it climbed the acquisition ladder. Two attempts, both recorded."

**1:15 to 2:30: Break something quiet (the important one)**

Trigger `selector_drift`.

> "This is the failure that actually costs money. The scrape returns HTTP 200. The pipeline is green. The data is empty. Most pipelines would ship this to a dashboard and nobody would notice for a week."

Show the assertion failing in the ledger.

> "The row-count assertion caught it. Class F2, structural drift."

Now the P2 walkthrough, slowly, because this is the technical high point:

> "It pulls the last raw snapshot from storage, no network call. It asks the model to regenerate the extraction mapping. Then, and this is the part that matters, it tests that new extractor against three historical snapshots it knows the correct answer for. The model does not get to grade its own homework. Two of three would not be good enough. It needs all three."

Green. Show the before/after in the heal ledger.

**2:30 to 3:15: Show the agent refusing**

Trigger `field_rename` on the JSON API. This is a Tier 2 repair.

> "Schema change. The agent is not allowed to do this alone."

Port approval card appears with the proposed diff and blast radius.

> "It stopped and asked. This is the part I care about most. An agent that can change your schema at 3am without asking is not a feature."

Approve. It completes.

**3:15 to 3:45: Show the agent giving up**

Permanent 403.

> "Same failure fingerprint three times in an hour. That is not transient, it is structural, so it stops trying. Circuit opens, incident escalates, owner gets paged. Knowing when to quit is a design requirement, not a bug."

**3:45 to 4:30: The generalization proof**

> "Everything so far was a source I set up. Let me add one now."

Register the holdout source live via the Port `register_source` action. Paste the contract JSON. It ingests.

> "New source. No deploy, no code change, one JSON file."

Now let a judge pick the fault from the injector menu.

> "Pick any of the eight."

It heals.

> "Same agent. Same eight primitives. A source that did not exist ninety seconds ago. That is what 'any kind of data' has to mean, otherwise it is just a demo of the specific thing I wrote a handler for."

**4:30 to 5:00: The numbers**

Scoreboard on screen.

> "Twelve incidents. MTTD 22 seconds median. MTTR 71 seconds median. 83% healed autonomously. One escalated on purpose. Zero false heals, and we track false heals, because an agent that claims success without verifying is worse than no agent."

**Fallbacks, prepared in advance:**

| If this breaks | Do this |
|---|---|
| SigNoz ingestion lags | Switch to the assertion-driven detection path; it is local and instant |
| Bright Data rate limit | Pre-seeded raw snapshots; P5 replay works fully offline |
| Port MCP auth expires | Local ledger view; re-auth after the demo |
| Everything breaks | Recorded video, cued and ready |

---

## 10. Risks, cut lines, and stretch goals

### Risks ranked by likelihood times damage

| Risk | Likelihood | Damage | Mitigation |
|---|---|---|---|
| OTel to SigNoz eats hours | High | High | Do it at T+0, verify a hello-world span before anything else |
| Live scraping fails on stage | Medium | High | Pre-seed raw snapshots; P5 replay works fully offline |
| Bright Data quota exhausted | Medium | Medium | Track with `session_stats`; cache aggressively; batch |
| LLM produces a bad extractor | Medium | Medium | The historical-snapshot guard already handles it; it is a designed outcome, not a failure |
| Agent thrashes | Low | High | Budget, fingerprint escalation, circuit breaker |
| MCP tool names drift | Low | High | Capability layer + startup probe |
| Demo runs long | High | Medium | Rehearse timed; cut S06 and S07 first |

### Cut lines, in the order you cut them

1. Cut the Port dashboard polish. The catalog itself is enough.
2. Cut primitives P7 and P4. Five primitives still prove the thesis.
3. Cut the CSV source. Two heterogeneous sources still make the point.
4. Cut the learning loop. Say it out loud as designed-but-unbuilt rather than faking it.
5. **Never cut:** the verifier, the guard, the generalization demo. Those three are the whole argument.

### Stretch goals, if you somehow have time

- **Auto-generated SigNoz alerts.** On `register_source`, call `signoz_create_alert` to provision freshness and error-rate alerts for the new source automatically.
- **Auto-generated SigNoz dashboard.** `signoz_create_dashboard` per source at registration.
- **Blast radius calculation.** Walk Port relations to show which downstream entities a Tier 2 change would touch, and put that in the approval card.
- **Cost-aware playbook ordering.** Weight primitives by Bright Data request cost, not just success probability.
- **Contract inference.** Point HYDRA at a URL with no contract and let it draft one from a sample fetch.

---

## Appendix A: environment and secrets

```bash
# .env.example additions for HYDRA

# ---------- Bright Data ----------
BRIGHTDATA_API_TOKEN=
BRIGHTDATA_GROUPS=advanced_scraping,browser,research
WEB_UNLOCKER_ZONE=
BROWSER_ZONE=

# ---------- SigNoz ----------
SIGNOZ_REGION=us
SIGNOZ_API_KEY=
SIGNOZ_INSTANCE_URL=https://your-org.signoz.cloud
SIGNOZ_INGESTION_KEY=
OTEL_EXPORTER_OTLP_ENDPOINT=https://ingest.us.signoz.cloud:443

# ---------- Port ----------
PORT_REGION=eu
PORT_CLIENT_ID=
PORT_CLIENT_SECRET=

# ---------- HYDRA ----------
HYDRA_MODE=replay
HYDRA_ENV=hackathon
HYDRA_DB_PATH=./hydra.duckdb
HYDRA_DETECT_INTERVAL_S=15
HYDRA_HEAL_BUDGET_PER_HOUR=5
HYDRA_FINGERPRINT_ESCALATION=3
HYDRA_APPROVAL_TIMEOUT_S=300
ANTHROPIC_API_KEY=
```

Preflight, run at T+0:

```bash
python scripts/hydra_probe.py
# Expected in replay:
#   OK  duckdb       schema initialized
#   OK  contracts    3 seed + 1 holdout valid
#   OK  capabilities bindings loaded
# Live mode additionally probes Port / SigNoz / Bright Data.
```

---

## Appendix B: Port blueprints (full JSON)

```json
{
  "identifier": "hydra_source",
  "title": "HYDRA Data Source",
  "icon": "Database",
  "schema": {
    "properties": {
      "kind":               { "type": "string", "enum": ["web_page", "json_api", "csv_file", "structured_feed"] },
      "url":                { "type": "string", "format": "url" },
      "contract_version":   { "type": "number" },
      "health":             { "type": "string", "enum": ["healthy", "degraded", "failed", "healing"] },
      "circuit_state":      { "type": "string", "enum": ["closed", "half_open", "open"] },
      "freshness_seconds":  { "type": "number" },
      "freshness_slo_seconds": { "type": "number" },
      "acquisition_rung":   { "type": "number" },
      "autonomy_tier_max":  { "type": "number" },
      "assertion_count":    { "type": "number" },
      "last_run_status":    { "type": "string" },
      "heals_last_7d":      { "type": "number" },
      "owner_team":         { "type": "string" }
    },
    "required": ["kind", "health", "contract_version"]
  },
  "calculationProperties": {
    "is_stale": {
      "title": "Stale",
      "type": "boolean",
      "calculation": ".properties.freshness_seconds > .properties.freshness_slo_seconds"
    }
  }
}
```

```json
{
  "identifier": "hydra_incident",
  "title": "HYDRA Incident",
  "icon": "Alert",
  "schema": {
    "properties": {
      "failure_class": { "type": "string", "enum": ["F1","F2","F3","F4","F5","F6"] },
      "fingerprint":   { "type": "string" },
      "detected_at":   { "type": "string", "format": "date-time" },
      "resolved_at":   { "type": "string", "format": "date-time" },
      "mttd_seconds":  { "type": "number" },
      "mttr_seconds":  { "type": "number" },
      "resolution":    { "type": "string", "enum": ["healed", "escalated", "blocked", "open"] },
      "attempts":      { "type": "number" },
      "trace_id":      { "type": "string" },
      "evidence":      { "type": "string", "format": "markdown" }
    },
    "required": ["failure_class", "fingerprint", "detected_at"]
  },
  "relations": {
    "source": { "target": "hydra_source", "required": true, "many": false }
  }
}
```

```json
{
  "identifier": "hydra_heal_action",
  "title": "HYDRA Heal Action",
  "icon": "Bolt",
  "schema": {
    "properties": {
      "primitive":           { "type": "string", "enum": ["P1","P2","P3","P4","P5","P6","P7","P8"] },
      "autonomy_tier":       { "type": "number" },
      "attempt":             { "type": "number" },
      "approved_by":         { "type": "string" },
      "verification_passed": { "type": "boolean" },
      "duration_seconds":    { "type": "number" },
      "before_state":        { "type": "string", "format": "markdown" },
      "after_state":         { "type": "string", "format": "markdown" },
      "contract_diff":       { "type": "string", "format": "markdown" },
      "brightdata_requests": { "type": "number" }
    },
    "required": ["primitive", "autonomy_tier"]
  },
  "relations": {
    "incident": { "target": "hydra_incident", "required": true, "many": false }
  }
}
```

```json
{
  "identifier": "hydra_self_healing_maturity",
  "title": "Self-Healing Maturity",
  "blueprint": "hydra_source",
  "rules": [
    {
      "identifier": "has_contract",
      "title": "Has a contract with at least 3 assertions",
      "level": "Bronze",
      "query": { "combinator": "and", "conditions": [
        { "property": "assertion_count", "operator": ">=", "value": 3 }
      ]}
    },
    {
      "identifier": "telemetry_and_freshness",
      "title": "Telemetry flowing and inside freshness SLO",
      "level": "Silver",
      "query": { "combinator": "and", "conditions": [
        { "property": "is_stale", "operator": "=", "value": false },
        { "property": "last_run_status", "operator": "=", "value": "ok" }
      ]}
    },
    {
      "identifier": "proven_autonomous_heal",
      "title": "At least one verified autonomous heal in 7 days",
      "level": "Gold",
      "query": { "combinator": "and", "conditions": [
        { "property": "heals_last_7d", "operator": ">=", "value": 1 },
        { "property": "circuit_state", "operator": "=", "value": "closed" }
      ]}
    }
  ]
}
```

---

## Appendix C: agent prompts

**Diagnoser prompt (Diagnose step):**

```
You are diagnosing a data pipeline failure. Work only from the evidence below.

SOURCE CONTRACT:
{contract_json}

TELEMETRY EVIDENCE (from SigNoz):
- Failing span:      {span_name}
- Status:            {span_status}
- Error:             {error_type}: {error_message}
- Rows parsed:       {rows_parsed} (baseline {rows_baseline})
- Failed assertions: {failed_assertions}

FRESH SAMPLE OF THE RAW PAYLOAD:
{raw_sample}

LAST KNOWN GOOD PAYLOAD (same source, {days_ago} days ago):
{good_sample}

Answer in JSON only:
{
  "what_changed": "one sentence, concrete and specific",
  "confidence": 0.0 to 1.0,
  "evidence": ["cite the specific difference you observed"],
  "recommended_primitive": "P1|P2|P3|P4|P5|P6|P7|P8",
  "reasoning": "one sentence"
}

Rules:
- If the two payloads look structurally identical, say so and set confidence low.
- Never claim a cause you cannot point to in the samples above.
- "I cannot tell from this evidence" is a valid and preferred answer when true.
```

**Guard summary prompt (for the Port approval card):**

```
Summarize this proposed repair for a human who has 20 seconds to decide.

PROPOSED CHANGE:
{contract_diff}

BLAST RADIUS:
{downstream_entities}

Write exactly three lines:
1. What will change (plain language, no jargon)
2. What breaks if this is wrong
3. How to undo it

No preamble. No hedging. If you cannot determine the blast radius, say
"blast radius unknown" on line 2 rather than guessing.
```

---

## Appendix D: verified MCP tool inventory

Checked against current documentation. Names drift, so the startup probe is the authority, not this table.

### Bright Data (`https://mcp.brightdata.com/mcp`)

| Group | Tools used by HYDRA |
|---|---|
| Rapid (free) | `search_engine`, `scrape_as_markdown` |
| `advanced_scraping` | `scrape_as_html`, `extract`, `scrape_batch`, `search_engine_batch`, `session_stats` |
| `browser` | `scraping_browser_navigate`, `_snapshot`, `_click_ref`, `_type_ref`, `_screenshot`, `_network_requests`, `_wait_for_ref`, `_get_text`, `_get_html`, `_scroll`, `_scroll_to_ref`, `_go_back`, `_go_forward` |
| Optional | `web_data_*` structured extractors, if a demo source is a supported platform |

The acquisition ladder maps directly onto this: `scrape_as_markdown` (rung 0) to `scrape_as_html` (rung 1) to `extract` (rung 2) to the browser session (rung 3).

### SigNoz (`https://mcp.<region>.signoz.cloud/mcp`)

| Category | Tools used by HYDRA |
|---|---|
| Discovery | `signoz_list_services`, `signoz_list_metrics`, `signoz_get_field_keys`, `signoz_get_field_values`, `signoz_get_org_overview` |
| Traces | `signoz_search_traces`, `signoz_aggregate_traces`, `signoz_get_trace_details`, `signoz_get_service_top_operations` |
| Logs | `signoz_search_logs`, `signoz_aggregate_logs` |
| Metrics | `signoz_query_metrics`, `signoz_check_metric_cardinality` |
| Alerts | `signoz_list_alerts`, `signoz_list_alert_rules`, `signoz_get_alert_history`, `signoz_create_alert` |
| Dashboards | `signoz_list_dashboards`, `signoz_create_dashboard`, `signoz_patch_dashboard` |
| Escape hatch | `signoz_execute_builder_query` (Query Builder v5, PromQL, ClickHouse SQL) |

Version floors worth knowing: dashboard tools need SigNoz v0.135.0+, alert-rule CRUD needs v0.120.0+, `signoz_get_alert_history` needs v0.118.0+. Older self-hosted deployments return 404.

### Port (`https://mcp.port.io/v1` EU, `https://mcp.us.port.io/v1` US)

| Category | Tools used by HYDRA |
|---|---|
| Data model | `list_blueprints`, `upsert_blueprint`, `list_entities`, `upsert_entity`, `delete_entity` |
| Actions | `list_actions`, `upsert_action`, `run_action`, `trigger_run`, `track_action_run`, `get_workflow_run`, `get_action_permissions` |
| Scorecards | `list_scorecards`, `upsert_scorecard` |
| Pages | `upsert_dashboard_page`, `upsert_widget`, `load_widget_schema` |
| General | `describe_user_details`, `search_port_knowledge_sources` |

Tool availability depends on the authenticated user's Port role. Builder tools (`upsert_*`) generally need admin. Set `x-read-only-mode: 0` and scope `x-allowed-actions-to-run` to exactly the six HYDRA actions.

---

## The one-slide summary

> **Problem:** external data breaks constantly, quietly, and differently every time. Retries are not healing.
>
> **Approach:** make sources declarative (contracts) and failures categorical (six classes). Repairs bind to classes, never to sources, so healing generalizes to data the agent has never seen.
>
> **Stack:** SigNoz senses, Bright Data acts on the data plane, Port remembers and governs.
>
> **Proof:** verified before/after on the same assertion that detected the failure, plus a live heal on a source registered ninety seconds earlier.
>
> **Honesty:** the agent knows when to stop, asks before it changes your schema, and reports its own false-heal rate.

## Relationship to the existing factory

`SPEC.md` still owns the HN digest, INV-1, DEC-07 (heal is triggered for the factory CLI), and `service.name = zero-downtime-factory`. HYDRA does not write `data/latest.json`. Default `HYDRA_MODE=replay` so the demo does not need venue wifi.
