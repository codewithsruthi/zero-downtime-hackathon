import { EXIT, getHnUrl, resolveCollectorId } from '../config.js';
import { loadState, transition } from '../state.js';
import { newApprovalId } from '../ids.js';
import { healScraper } from '../adapters/brightdata/index.js';
import { withSpan } from '../telemetry/otel.js';
import { upsertEntity } from '../adapters/port/index.js';

export async function healCommand(ctx) {
  const { root, flags, env, log } = ctx;
  const collectorId = resolveCollectorId({ flag: flags.collectorId, root, env });
  const url = flags.url || getHnUrl(env);
  const prompt = flags.prompt || 'HN markup changed. Re-capture title, url, points, author, comment_count. Keep job posts.';
  let state = loadState(root);

  if (flags.dryRun) {
    log.info('dry-run heal', { collectorId, from: state.status });
    return { exitCode: EXIT.SUCCESS, result: { dryRun: true, collectorId } };
  }

  return withSpan('factory.heal', { 'factory.component': 'pipeline' }, async (span) => {
    span?.addEvent?.('factory.heal.requested', { collector_id: collectorId });
    if (state.status === 'DEGRADED') {
      state = transition(root, 'BROKEN', { last_error: 'heal requested from DEGRADED' });
    }
    if (state.status !== 'BROKEN' && state.status !== 'PENDING_APPROVAL' && state.status !== 'HEALING') {
      const err = new Error(`heal requires BROKEN (or DEGRADED), currently ${state.status}`);
      return { exitCode: EXIT.ILLEGAL_TRANSITION, result: { error: err.message } };
    }
    if (state.status === 'BROKEN' || state.status === 'PENDING_APPROVAL') {
      try {
        state = transition(root, 'HEALING', { verification_failed: false, collector_id: collectorId });
      } catch (err) {
        return { exitCode: err.exitCode || EXIT.ILLEGAL_TRANSITION, result: { error: err.message } };
      }
    }

    const healed = await healScraper({ root, collectorId, url, prompt, env });
    if (healed.code !== 'OK' || healed.parsed == null) {
      try {
        transition(root, 'BROKEN', { verification_failed: true, last_error: healed.code || 'heal failed' });
      } catch {
        // already broken
      }
      span?.addEvent?.('factory.failure', { reason: 'heal_verification' });
      return { exitCode: EXIT.HEAL, result: { code: healed.code, verification_failed: true } };
    }

    const approvalId = newApprovalId();
    state = transition(root, 'PENDING_APPROVAL', {
      verification_failed: false,
      collector_id: collectorId,
      approval: {
        id: approvalId,
        status: 'pending',
        requested_at: new Date().toISOString(),
        resolved_at: null,
      },
    });
    span?.addEvent?.('factory.heal.pending', { approval_id: approvalId });
    await upsertEntity(root, 'approval', approvalId, {
      collector_id: collectorId,
      status: 'pending',
    }, env).catch(() => {});
    log.info('heal awaiting approval', { collectorId, approvalId });
    return { exitCode: EXIT.SUCCESS, result: { collectorId, approvalId, preview: healed.parsed, state } };
  });
}
