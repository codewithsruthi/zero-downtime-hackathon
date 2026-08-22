import { EXIT } from '../config.js';
import { promoteCandidate } from '../pipeline/promote.js';

export async function promoteCommand(ctx) {
  const { root, flags, log } = ctx;
  if (flags.dryRun) {
    log.info('dry-run promote');
    return { exitCode: EXIT.SUCCESS, result: { dryRun: true } };
  }
  try {
    const result = await promoteCandidate(root, { force: flags.force });
    log.info('promoted', { runId: result.candidate.run_id, stories: result.candidate.story_count });
    return { exitCode: EXIT.SUCCESS, result };
  } catch (err) {
    return { exitCode: err.exitCode || EXIT.GENERIC, result: { error: err.message, report: err.report } };
  }
}
