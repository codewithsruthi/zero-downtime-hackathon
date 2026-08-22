import fs from 'node:fs';
import path from 'node:path';
import { EXIT, paths, ensureDataDirs } from '../config.js';
import { atomicWriteJson } from '../atomic.js';
import { validate, failedGateIds } from './validate.js';
import { loadState, promotionBlocked, recordSuccess } from '../state.js';
import { withSpan } from '../telemetry/otel.js';

export function snapshotLatest(root) {
  const p = paths(root);
  if (!fs.existsSync(p.latest)) return null;
  const dest = path.join(p.snapshots, `latest-${Date.now()}.json`);
  fs.mkdirSync(p.snapshots, { recursive: true });
  fs.copyFileSync(p.latest, dest);
  return dest;
}

export async function promoteCandidate(root, { force = false } = {}) {
  return withSpan('factory.promote', { 'factory.component': 'pipeline' }, async (span) => {
    const p = ensureDataDirs(root);
    if (!fs.existsSync(p.candidate)) {
      const err = new Error('data/candidate.json is missing; scrape first');
      err.exitCode = EXIT.FILE;
      throw err;
    }
    let candidate;
    try {
      candidate = JSON.parse(fs.readFileSync(p.candidate, 'utf8'));
    } catch (err) {
      const wrapped = new Error(`candidate.json is not valid JSON: ${err.message}`);
      wrapped.exitCode = EXIT.PARSE;
      throw wrapped;
    }
    const report = validate(candidate);
    span?.setAttribute?.('factory.validation.ok', report.ok);
    span?.setAttribute?.('factory.validation.failed_gates', failedGateIds(report).join(','));
    if (!report.ok) {
      const err = new Error(`validation failed: ${report.errors.map((e) => e.gate).join(',')}`);
      err.exitCode = EXIT.VALIDATION;
      err.report = report;
      throw err;
    }
    const state = loadState(root);
    if (!force && promotionBlocked(state)) {
      const err = new Error('promotion blocked by approval gate');
      err.exitCode = EXIT.NOT_APPROVED;
      throw err;
    }
    snapshotLatest(root);
    atomicWriteJson(p.latest, candidate);
    const next = recordSuccess(root, {
      runId: candidate.run_id,
      collectorId: candidate.collector_id,
    });
    span?.addEvent?.('factory.promoted', { run_id: candidate.run_id });
    return { candidate, state: next, report };
  });
}
