#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MAJOR="$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || echo 0)"
if [ "$MAJOR" -lt 20 ]; then
  echo "Node.js 20+ is required. Found $(node --version 2>/dev/null || echo none)." >&2
  exit 1
fi

npm install
npm --prefix app install --omit=dev --no-package-lock || npm --prefix app install

# EC-PROBE-02: pin and pre-warm the Bright Data CLI
npx -p @brightdata/cli@0.3.5 bdata --version || true

mkdir -p data/raw data/snapshots data/sample-output port/state
echo "setup ok (node $(node --version), cli pinned 0.3.5)"
