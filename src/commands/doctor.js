import fs from 'node:fs';
import path from 'node:path';
import { EXIT, getMode, getRoot, paths, resolveCollectorId } from '../config.js';
import { loadState } from '../state.js';
import { validate } from '../pipeline/validate.js';
import { EXPORT_TIMEOUT_MS } from '../telemetry/otel.js';

async function checkOtel(env) {
  const endpoint = env.OTEL_EXPORTER_OTLP_ENDPOINT;
  if (!endpoint || env.FACTORY_OTEL_DISABLED === '1') {
    return { ok: true, skipped: true, detail: 'OTEL endpoint unset or disabled' };
  }
  const url = `${endpoint.replace(/\/$/, '')}/v1/traces`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), EXPORT_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
      signal: ctrl.signal,
    });
    return { ok: true, skipped: false, status: res.status, detail: 'endpoint accepted a probe' };
  } catch (err) {
    return { ok: true, skipped: false, detail: `unreachable (${err.message}); pipeline will swallow export errors` };
  } finally {
    clearTimeout(timer);
  }
}

export async function doctorCommand(ctx) {
  const { root, env } = ctx;
  const p = paths(root);
  const checks = [];
  const nodeMajor = Number(process.versions.node.split('.')[0]);
  checks.push({ name: 'node', ok: nodeMajor >= 20, detail: process.version });

  let collector = null;
  try {
    collector = resolveCollectorId({ root, env, flag: ctx.flags.collectorId });
    checks.push({ name: 'collector_id', ok: true, detail: collector });
  } catch (err) {
    checks.push({ name: 'collector_id', ok: false, detail: err.message });
  }

  checks.push({ name: 'data_dir', ok: true, detail: p.data });
  const state = loadState(root);
  checks.push({ name: 'state', ok: true, detail: state.status });

  if (fs.existsSync(p.latest)) {
    try {
      const report = validate(JSON.parse(fs.readFileSync(p.latest, 'utf8')));
      checks.push({ name: 'latest.json', ok: report.ok, detail: report.ok ? 'valid' : report.errors.map((e) => e.gate).join(',') });
    } catch (err) {
      checks.push({ name: 'latest.json', ok: false, detail: err.message });
    }
  } else {
    checks.push({ name: 'latest.json', ok: true, detail: 'absent (legal)' });
  }

  checks.push({ name: 'mode', ok: true, detail: getMode(env) });
  checks.push({ name: 'otel', ...(await checkOtel(env)) });
  try {
    fs.mkdirSync(path.dirname(p.ledger), { recursive: true });
    checks.push({ name: 'ledger_dir', ok: true, detail: p.ledger });
  } catch (err) {
    checks.push({ name: 'ledger_dir', ok: false, detail: err.message });
  }

  const ok = checks.every((c) => c.ok);
  return { exitCode: ok ? EXIT.SUCCESS : EXIT.GENERIC, result: { checks, root: getRoot(env), collector } };
}
