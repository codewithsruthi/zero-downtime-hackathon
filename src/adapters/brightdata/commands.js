// SINGLE SOURCE OF TRUTH for Bright Data CLI syntax.
// If the CLI surface differs from the probe, edit ONLY this file.
// Pinned from scripts/probe.sh: @brightdata/cli@0.3.5
// Deviations (docs/cli-surface.md):
//   - reject is `scraper approve --reject`, not a reject subcommand
//   - never pass --auto-approve (DEC-07)

export const PINNED_VERSION = '0.3.5';

export const CLI = {
  bin: 'npx',
  baseArgs: ['-p', `@brightdata/cli@${PINNED_VERSION}`, 'bdata'],
  create: ({ url, prompt }) => ['scraper', 'create', url, prompt],
  run: ({ collectorId, url, outPath }) =>
    ['scraper', 'run', collectorId, url, '--pretty', '-o', outPath],
  heal: ({ collectorId, prompt, url }) =>
    ['scraper', 'heal', collectorId, prompt, '--url', url],
  approve: ({ collectorId, url }) =>
    ['scraper', 'approve', collectorId, '--url', url],
  reject: ({ collectorId }) =>
    ['scraper', 'approve', collectorId, '--reject'],
};
