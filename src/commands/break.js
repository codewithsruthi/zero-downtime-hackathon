import fs from 'node:fs';
import { EXIT, ensureDataDirs, paths } from '../config.js';
import { loadState, transition } from '../state.js';
import { withSpan } from '../telemetry/otel.js';

export async function breakCommand(ctx) {
  const { root, flags, log } = ctx;
  const p = ensureDataDirs(root);
  if (flags.dryRun) return { exitCode: EXIT.SUCCESS, result: { dryRun: true } };

  return withSpan('factory.break', { 'factory.component': 'pipeline' }, async () => {
    fs.writeFileSync(p.brokenMarker, `broken at ${new Date().toISOString()}\n`);
    if (fs.existsSync(p.healedMarker)) fs.unlinkSync(p.healedMarker);
    const state = loadState(root);
    let next = state;
    if (state.status !== 'BROKEN') {
      try {
        next = transition(root, 'BROKEN', { last_error: 'factory break', consecutive_failures: Math.max(state.consecutive_failures, 1) });
      } catch (err) {
        return { exitCode: err.exitCode || EXIT.ILLEGAL_TRANSITION, result: { error: err.message } };
      }
    }
    log.info('break armed; next replay scrape uses broken.json');
    return { exitCode: EXIT.SUCCESS, result: { state: next, broken: p.brokenMarker } };
  });
}
