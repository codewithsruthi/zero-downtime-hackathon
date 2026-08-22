#!/usr/bin/env bash
# Offline-rehearsable break → heal → approve → re-run story.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export FACTORY_MODE="${FACTORY_MODE:-replay}"
export FACTORY_OTEL_DISABLED="${FACTORY_OTEL_DISABLED:-1}"
export FACTORY_APP_PORT="${FACTORY_APP_PORT:-34777}"
export FACTORY_COLLECTOR_ID="${FACTORY_COLLECTOR_ID:-c_hn_digest_factory}"
if [ -z "${TRACEPARENT:-}" ]; then
  TRACEPARENT="$(node -e "const c=require('crypto');console.log('00-'+c.randomBytes(16).toString('hex')+'-'+c.randomBytes(8).toString('hex')+'-01')")"
  export TRACEPARENT
fi

./scripts/reset.sh

node --import ./app/instrumentation.js app/server.js &
APP_PID=$!
cleanup() { kill "$APP_PID" 2>/dev/null || true; }
trap cleanup EXIT

ok=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if curl -sf "http://127.0.0.1:${FACTORY_APP_PORT}/api/health" >/dev/null; then
    ok=1
    break
  fi
  sleep 0.25
done
if [ "$ok" -ne 1 ]; then
  echo "app did not become healthy on port ${FACTORY_APP_PORT}" >&2
  exit 1
fi

./bin/factory run --json
curl -sf "http://127.0.0.1:${FACTORY_APP_PORT}/api/stories" | grep -q title

./bin/factory break --json
if ./bin/factory scrape --json; then
  echo "scrape should have failed after break" >&2
  exit 1
fi
curl -sf "http://127.0.0.1:${FACTORY_APP_PORT}/api/health" >/dev/null
curl -sf "http://127.0.0.1:${FACTORY_APP_PORT}/" | grep -qi digest

./bin/factory heal --json
if ./bin/factory promote --json; then
  echo "promote should be blocked before approve" >&2
  exit 1
fi

./bin/factory approve --json
./bin/factory run --json
curl -sf "http://127.0.0.1:${FACTORY_APP_PORT}/api/stories" | grep -q title

echo "DEMO_OK collector=${FACTORY_COLLECTOR_ID} traceparent=${TRACEPARENT}"
