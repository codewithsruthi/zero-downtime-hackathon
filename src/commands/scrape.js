import { EXIT, ensureDataDirs, getHnUrl, requireLiveKey, resolveCollectorId } from '../config.js';
import { withLock } from '../lock.js';
import { newRunId } from '../ids.js';
import { atomicWriteJson } from '../atomic.js';
import { loadState, assertCircuitClosed, recordFailure, saveState } from '../state.js';
import { runScraper } from '../adapters/brightdata/index.js';
import { normalize } from '../pipeline/normalize.js';
import { validate, failedGateIds } from '../pipeline/validate.js';
import { withSpan } from '../telemetry/otel.js';
import { upsertEntity } from '../adapters/port/index.js';

export async function scrapeCommand(ctx) {
  const { root, flags, env, log } = ctx;
  requireLiveKey(env);
  const collectorId = resolveCollectorId({ flag: flags.collectorId, root, env });
  const url = flags.url || getHnUrl(env);
  const p = ensureDataDirs(root);
  const state = loadState(root);
  assertCircuitClosed(state);

  if (flags.dryRun) {
    log.info('dry-run scrape', { collectorId, url, mode: env.FACTORY_MODE || 'replay' });
    return { exitCode: EXIT.SUCCESS, result: { dryRun: true, collectorId, url } };
  }

  return withLock(p.lock, async () => withSpan('factory.scrape', { 'factory.component': 'pipeline' }, async (span) => {
    const runId = newRunId();
    span?.setAttribute?.('factory.run_id', runId);
    span?.setAttribute?.('factory.collector_id', collectorId);
    const scraped = await runScraper({ root, collectorId, url, runId, env });
    saveState({ ...loadState(root), last_run_id: runId, collector_id: collectorId }, root);

    if (scraped.code !== 'OK') {
      recordFailure(root, scraped.code, { hard: scraped.code === 'FAIL_PARSE' || scraped.code === 'FAIL_AUTH' });
      const exitCode = scraped.code === 'FAIL_PARSE' ? EXIT.PARSE : EXIT.SCRAPE;
      log.error('scrape failed', { code: scraped.code, runId });
      return { exitCode, result: { runId, collectorId, code: scraped.code } };
    }

    const doc = await withSpan('factory.normalize', { 'factory.component': 'pipeline' }, async () =>
      normalize(scraped.parsed, { collectorId, runId, source: url }),
    );
    const report = await withSpan('factory.validate', { 'factory.component': 'pipeline' }, async (vspan) => {
      const r = validate(doc);
      vspan?.setAttribute?.('factory.validation.ok', r.ok);
      vspan?.setAttribute?.('factory.validation.failed_gates', failedGateIds(r).join(','));
      return r;
    });
    atomicWriteJson(p.candidate, doc);
    await upsertEntity(root, 'factory_run', runId, {
      collector_id: collectorId,
      status: report.ok ? 'validated' : 'invalid',
      story_count: doc.story_count,
    }, env).catch(() => {});

    if (!report.ok) {
      recordFailure(root, `validation ${failedGateIds(report).join(',')}`, { hard: false });
      log.error('validate failed', { gates: failedGateIds(report), runId });
      return { exitCode: EXIT.VALIDATION, result: { runId, collectorId, report, candidate: p.candidate } };
    }

    log.info('scrape ok', { runId, stories: doc.story_count, candidate: p.candidate });
    return { exitCode: EXIT.SUCCESS, result: { runId, collectorId, doc, report } };
  }));
}
