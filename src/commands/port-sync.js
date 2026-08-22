import { EXIT, DEFAULT_COLLECTOR_ID, resolveCollectorId } from '../config.js';
import { loadState } from '../state.js';
import { syncNow } from '../adapters/port/index.js';

export async function portSyncCommand(ctx) {
  const { root, flags, env, log } = ctx;
  let collectorId = DEFAULT_COLLECTOR_ID;
  try {
    collectorId = resolveCollectorId({ flag: flags.collectorId, root, env });
  } catch {
    // still sync with default
  }
  const state = loadState(root);
  const entities = [
    { type: 'service', id: 'hn-digest', props: { status: state.status, component: 'app' } },
    { type: 'scraper', id: collectorId, props: { collector_id: collectorId, status: state.status } },
    { type: 'factory_run', id: state.last_run_id || 'none', props: { status: state.status, collector_id: collectorId } },
    {
      type: 'approval',
      id: state.approval?.id || 'none',
      props: { status: state.approval?.status || 'none', collector_id: collectorId },
    },
  ];
  if (flags.dryRun) return { exitCode: EXIT.SUCCESS, result: { dryRun: true, entities } };
  const written = await syncNow(root, entities, env);
  log.info('port sync wrote ledger', { count: written.length });
  return { exitCode: EXIT.SUCCESS, result: { written } };
}
