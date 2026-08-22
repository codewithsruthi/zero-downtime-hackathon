import fs from 'node:fs';
import path from 'node:path';
import { EXIT, paths, ensureDataDirs } from '../config.js';
import { atomicWriteJson } from '../atomic.js';
import { validate } from '../pipeline/validate.js';
import { loadState, recordSuccess } from '../state.js';
import { withSpan } from '../telemetry/otel.js';

export async function rollbackCommand(ctx) {
  const { root, flags, log } = ctx;
  const p = ensureDataDirs(root);
  if (flags.dryRun) return { exitCode: EXIT.SUCCESS, result: { dryRun: true } };

  return withSpan('factory.rollback', { 'factory.component': 'pipeline' }, async () => {
    const files = fs.existsSync(p.snapshots)
      ? fs.readdirSync(p.snapshots).filter((f) => f.endsWith('.json')).sort()
      : [];
    if (!files.length) {
      return { exitCode: EXIT.FILE, result: { error: 'no snapshots to roll back to' } };
    }
    const latestSnap = path.join(p.snapshots, files[files.length - 1]);
    let doc;
    try {
      doc = JSON.parse(fs.readFileSync(latestSnap, 'utf8'));
    } catch (err) {
      return { exitCode: EXIT.PARSE, result: { error: err.message } };
    }
    const report = validate(doc);
    if (!report.ok) {
      return { exitCode: EXIT.VALIDATION, result: { error: 'snapshot failed validation', report } };
    }
    atomicWriteJson(p.latest, doc);
    const state = loadState(root);
    if (state.status === 'HEALTHY' || state.status === 'DEGRADED' || state.status === 'RECOVERED' || state.status === 'UNKNOWN') {
      recordSuccess(root, { runId: doc.run_id, collectorId: doc.collector_id });
    }
    log.info('rolled back', { snapshot: latestSnap, runId: doc.run_id });
    return { exitCode: EXIT.SUCCESS, result: { snapshot: latestSnap, doc } };
  });
}
