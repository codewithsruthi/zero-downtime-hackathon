#!/usr/bin/env bash
# REQ-PROBE-01: capture real Bright Data CLI --help output.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/cli-surface.md"
mkdir -p "$ROOT/docs"

{
  echo "# Bright Data CLI surface"
  echo
  echo "Captured: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "Node: $(node --version 2>/dev/null || echo missing)"
  echo "Pinned package: @brightdata/cli@0.3.5"
  echo
  echo "If the live surface differs from the assumed flags, edit ONLY"
  echo "src/adapters/brightdata/commands.js (EC-PROBE-01)."
  echo
  echo "## node --version"
  echo
  echo '```'
  node --version || true
  echo '```'
  echo
  echo "## npx -p @brightdata/cli@0.3.5 bdata --help"
  echo
  echo '```'
  npx -p @brightdata/cli@0.3.5 bdata --help || true
  echo '```'
  echo
  echo "## npx -p @brightdata/cli@0.3.5 bdata scraper --help"
  echo
  echo '```'
  npx -p @brightdata/cli@0.3.5 bdata scraper --help || true
  echo '```'
  echo
  echo "## npx -p @brightdata/cli@0.3.5 bdata scraper create --help"
  echo
  echo '```'
  npx -p @brightdata/cli@0.3.5 bdata scraper create --help || true
  echo '```'
  echo
  echo "## npx -p @brightdata/cli@0.3.5 bdata scraper run --help"
  echo
  echo '```'
  npx -p @brightdata/cli@0.3.5 bdata scraper run --help || true
  echo '```'
  echo
  echo "## npx -p @brightdata/cli@0.3.5 bdata scraper heal --help"
  echo
  echo '```'
  npx -p @brightdata/cli@0.3.5 bdata scraper heal --help || true
  echo '```'
  echo
  echo "## npx -p @brightdata/cli@0.3.5 bdata scraper approve --help"
  echo
  echo '```'
  npx -p @brightdata/cli@0.3.5 bdata scraper approve --help || true
  echo '```'
  echo
  echo "## Resolved version"
  echo
  echo '```'
  npx -p @brightdata/cli@0.3.5 bdata --version || true
  echo '```'
  echo
  echo "## Deviations from the source-doc assumed flags"
  echo
  echo "Filled after probe. See the bottom of this file."
} | tee "$OUT"

exit 0
