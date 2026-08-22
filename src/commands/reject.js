import { EXIT, resolveCollectorId } from '../config.js';
import { loadState, transition } from '../state.js';
import { rejectScraper } from '../adapters/brightdata/index.js';
import { withSpan } from '../telemetry/otel.js';
import { upsertEntity } from '../adapters/port/index.js';

export async function rejectCommand(ctx) {
  const { root, flags, env, log } = ctx;
  const collectorId = resolveCollectorId({ flag: flags.collectorId, root, env });
  const state = loadState(root);
  if (flags.dryRun) return { exitCode: EXIT.SUCCESS, result: { dryRun: true } };

  return withSpan('factory.reject', { 'factory.component': 'pipeline' }, async () => {
    if (state.status !== 'PENDING_APPROVAL') {
      return {
        exitCode: EXIT.ILLEGAL_TRANSITION,
        result: { error: `reject requires PENDING_APPROVAL, currently ${state.status}` },
      };
    }
    await rejectScraper({ collectorId, env });
    const next = transition(root, 'BROKEN', {
      approval: {
        ...state.approval,
        status: 'rejected',
        resolved_at: new Date().toISOString(),
      },
    });
    if (state.approval?.id) {
      await upsertEntity(root, 'approval', state.approval.id, { status: 'rejected', collector_id: collectorId }, env).catch(() => {});
    }
    log.info('rejected', { collectorId });
    return { exitCode: EXIT.SUCCESS, result: { collectorId, state: next } };
  });
}
