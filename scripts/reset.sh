#!/usr/bin/env bash
# EC-DEMO-01: restore replay fixtures, clear lock/broken/state/latest/candidate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
rm -f \
  "$ROOT/data/latest.json" \
  "$ROOT/data/candidate.json" \
  "$ROOT/data/state.json" \
  "$ROOT/data/.factory.lock" \
  "$ROOT/data/.broken" \
  "$ROOT/data/.healed"
rm -rf "$ROOT/data/raw" "$ROOT/data/snapshots"
mkdir -p "$ROOT/data/raw" "$ROOT/data/snapshots" "$ROOT/port/state"
# keep data/sample-output and port blueprints
find "$ROOT/data/raw" "$ROOT/data/snapshots" -type f -delete || true
: > "$ROOT/port/state/ledger.jsonl" || true
echo "reset ok"
