import { EXIT } from '../config.js';
import { flushLedger } from '../adapters/port/index.js';

export async function portFlushCommand(ctx) {
  const { root, flags, env, log } = ctx;
  if (flags.dryRun) return { exitCode: EXIT.SUCCESS, result: { dryRun: true } };
  const entries = await flushLedger(root, env);
  log.info('port flush complete', { count: entries.length });
  return { exitCode: EXIT.SUCCESS, result: { entries } };
}
