import fs from 'node:fs';
import { EXIT, getHnUrl, paths, resolveCollectorId } from '../config.js';
import { loadState, transition } from '../state.js';
import { approveScraper } from '../adapters/brightdata/index.js';
import { withSpan } from '../telemetry/otel.js';
import { upsertEntity } from '../adapters/port/index.js';

export async function approveCommand(ctx) {
  const { root, flags, env, log } = ctx;
  const collectorId = resolveCollectorId({ flag: flags.collectorId, root, env });
  const url = flags.url || getHnUrl(env);
  const state = loadState(root);

  if (flags.dryRun) {
    return { exitCode: EXIT.SUCCESS, result: { dryRun: true, collectorId } };
  }

  return withSpan('factory.approve', { 'factory.component': 'pipeline' }, async (span) => {
    if (state.status !== 'PENDING_APPROVAL') {
      return {
        exitCode: EXIT.ILLEGAL_TRANSITION,
        result: { error: `approve requires PENDING_APPROVAL, currently ${state.status}` },
      };
    }
    const approved = await approveScraper({ root, collectorId, url, env });
    if (approved.code !== 'OK') {
      return { exitCode: EXIT.HEAL, result: { code: approved.code } };
    }
    const p = paths(root);
    if (fs.existsSync(p.brokenMarker)) fs.unlinkSync(p.brokenMarker);
    fs.writeFileSync(p.healedMarker, `${new Date().toISOString()}\n`);
    const next = transition(root, 'RECOVERED', {
      collector_id: collectorId,
      consecutive_failures: 0,
      circuit_open: false,
      approval: {
        ...state.approval,
        status: 'approved',
        resolved_at: new Date().toISOString(),
      },
    });
    span?.addEvent?.('factory.approved', { collector_id: collectorId });
    if (state.approval?.id) {
      await upsertEntity(root, 'approval', state.approval.id, { status: 'approved', collector_id: collectorId }, env).catch(() => {});
    }
    log.info('approved', { collectorId, status: next.status });
    return { exitCode: EXIT.SUCCESS, result: { collectorId, state: next } };
  });
}
