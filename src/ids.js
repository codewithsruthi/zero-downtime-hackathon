import crypto from 'node:crypto';

export function newRunId(now = new Date()) {
  const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  return `run-${stamp}-${crypto.randomBytes(3).toString('hex')}`;
}

export function newApprovalId(now = new Date()) {
  const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  return `apr-${stamp}-${crypto.randomBytes(3).toString('hex')}`;
}

export function stableId(parts) {
  const h = crypto.createHash('sha1').update(parts.join('|')).digest('hex').slice(0, 12);
  return `hn-${h}`;
}

export function newTraceIds() {
  return {
    traceId: crypto.randomBytes(16).toString('hex'),
    spanId: crypto.randomBytes(8).toString('hex'),
  };
}
