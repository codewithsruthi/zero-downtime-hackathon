import { appendLedger, readLedger, rewriteLedger } from './ledger.js';
import { mcpUpsert } from './mcp.js';
import { restUpsert } from './rest.js';
import { withSpan } from '../../telemetry/otel.js';
import { createLogger } from '../../logger.js';

const log = createLogger();
let remoteFailLogged = false;

export async function upsertEntity(root, type, id, props, env = process.env) {
  return withSpan('factory.port.upsert', { 'factory.component': 'pipeline', 'port.type': type }, async () => {
    const line = appendLedger(root, { op: 'upsert', type, id, props });
    try {
      let remote = await mcpUpsert({ type, id, props, env });
      if (remote.skipped) remote = await restUpsert({ type, id, props, env });
      line.remote_ok = Boolean(remote.ok);
      line.remote_error = remote.ok ? null : remote.error || 'remote failed';
      const entries = readLedger(root);
      if (entries.length) {
        entries[entries.length - 1] = line;
        rewriteLedger(root, entries);
      }
    } catch (err) {
      line.remote_ok = false;
      line.remote_error = err.message;
      if (!remoteFailLogged) {
        log.warn('port remote upsert failed; ledger kept', { error: err.message });
        remoteFailLogged = true;
      }
    }
    return line;
  });
}

export async function flushLedger(root, env = process.env) {
  const entries = readLedger(root);
  const next = [];
  for (const line of entries) {
    if (line.remote_ok) {
      next.push(line);
      continue;
    }
    let remote = await mcpUpsert({ type: line.type, id: line.id, props: line.props, env });
    if (remote.skipped) remote = await restUpsert({ type: line.type, id: line.id, props: line.props, env });
    next.push({
      ...line,
      remote_ok: Boolean(remote.ok),
      remote_error: remote.ok ? null : remote.error || line.remote_error,
      flushed_at: new Date().toISOString(),
    });
  }
  rewriteLedger(root, next);
  return next;
}

export async function syncNow(root, entities, env = process.env) {
  const written = [];
  for (const ent of entities) {
    written.push(await upsertEntity(root, ent.type, ent.id, ent.props, env));
  }
  return written;
}

export { readLedger, appendLedger };
