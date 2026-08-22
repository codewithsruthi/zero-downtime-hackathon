import fs from 'node:fs';
import { EXIT, paths, ensureDataDirs, getRoot } from './config.js';
import { atomicWriteJson } from './atomic.js';

export const STATUSES = [
  'UNKNOWN',
  'HEALTHY',
  'DEGRADED',
  'BROKEN',
  'HEALING',
  'PENDING_APPROVAL',
  'RECOVERED',
];

const LEGAL = {
  UNKNOWN: new Set(['UNKNOWN', 'HEALTHY', 'DEGRADED', 'BROKEN']),
  HEALTHY: new Set(['HEALTHY', 'DEGRADED', 'BROKEN']),
  DEGRADED: new Set(['HEALTHY', 'DEGRADED', 'BROKEN']),
  BROKEN: new Set(['BROKEN', 'HEALING']),
  HEALING: new Set(['HEALING', 'PENDING_APPROVAL', 'BROKEN']),
  PENDING_APPROVAL: new Set(['PENDING_APPROVAL', 'RECOVERED', 'BROKEN', 'HEALING']),
  RECOVERED: new Set(['RECOVERED', 'HEALTHY', 'BROKEN', 'DEGRADED']),
};

export function emptyState(now = new Date()) {
  return {
    schema_version: 1,
    status: 'UNKNOWN',
    consecutive_failures: 0,
    circuit_open: false,
    collector_id: null,
    last_run_id: null,
    last_good_run_id: null,
    last_error: null,
    verification_failed: false,
    approval: {
      id: null,
      status: 'none',
      requested_at: null,
      resolved_at: null,
    },
    updated_at: now.toISOString(),
  };
}

export function isLegalTransition(from, to) {
  return Boolean(LEGAL[from] && LEGAL[from].has(to));
}

export function illegalTransitionError(from, to) {
  const err = new Error(`Illegal state transition ${from} → ${to}`);
  err.exitCode = EXIT.ILLEGAL_TRANSITION;
  err.from = from;
  err.to = to;
  return err;
}

function looksLikeLatest(doc) {
  return (
    doc &&
    typeof doc === 'object' &&
    doc.schema_version === 1 &&
    Array.isArray(doc.stories) &&
    doc.stories.length >= 1 &&
    typeof doc.run_id === 'string' &&
    doc.run_id.length > 0
  );
}

export function reconstructState(root = getRoot()) {
  const p = paths(root);
  const base = emptyState();
  if (fs.existsSync(p.latest)) {
    try {
      const latest = JSON.parse(fs.readFileSync(p.latest, 'utf8'));
      if (looksLikeLatest(latest)) {
        base.status = 'HEALTHY';
        base.consecutive_failures = 0;
        base.circuit_open = false;
        base.last_good_run_id = latest.run_id || null;
        base.last_run_id = latest.run_id || null;
        base.collector_id = latest.collector_id || null;
      }
    } catch {
      // stay UNKNOWN
    }
  }
  return base;
}

export function loadState(root = getRoot()) {
  const p = ensureDataDirs(root);
  if (!fs.existsSync(p.state)) {
    return reconstructState(root);
  }
  try {
    const raw = JSON.parse(fs.readFileSync(p.state, 'utf8'));
    if (!raw || typeof raw !== 'object' || !STATUSES.includes(raw.status)) {
      return reconstructState(root);
    }
    return { ...emptyState(), ...raw, approval: { ...emptyState().approval, ...(raw.approval || {}) } };
  } catch {
    return reconstructState(root);
  }
}

export function saveState(state, root = getRoot()) {
  const p = ensureDataDirs(root);
  const next = {
    ...state,
    updated_at: new Date().toISOString(),
    circuit_open: state.consecutive_failures >= 3,
  };
  atomicWriteJson(p.state, next);
  return next;
}

export function transition(root, to, patch = {}) {
  const current = loadState(root);
  const from = current.status;
  if (!isLegalTransition(from, to)) {
    throw illegalTransitionError(from, to);
  }
  const next = {
    ...current,
    ...patch,
    status: to,
    approval: { ...current.approval, ...(patch.approval || {}) },
  };
  if (typeof next.consecutive_failures === 'number') {
    next.circuit_open = next.consecutive_failures >= 3;
  }
  return saveState(next, root);
}

export function recordFailure(root, error, { hard = false } = {}) {
  const current = loadState(root);
  const fails = (current.consecutive_failures || 0) + 1;
  const circuit = fails >= 3;
  let to = current.status;
  if (current.status === 'UNKNOWN' || current.status === 'HEALTHY') {
    to = hard || circuit ? 'BROKEN' : 'DEGRADED';
  } else if (current.status === 'DEGRADED') {
    to = circuit || hard ? 'BROKEN' : 'DEGRADED';
  } else if (current.status === 'RECOVERED') {
    to = hard || circuit ? 'BROKEN' : 'DEGRADED';
  } else if (current.status === 'BROKEN' || current.status === 'HEALING') {
    to = 'BROKEN';
  }
  return transition(root, to, {
    consecutive_failures: fails,
    circuit_open: circuit,
    last_error: error,
    verification_failed: current.status === 'HEALING' ? true : current.verification_failed,
  });
}

export function recordSuccess(root, { runId, collectorId }) {
  const current = loadState(root);
  const to = current.status === 'RECOVERED' ? 'HEALTHY' : 'HEALTHY';
  return transition(root, to, {
    consecutive_failures: 0,
    circuit_open: false,
    last_run_id: runId,
    last_good_run_id: runId,
    last_error: null,
    verification_failed: false,
    collector_id: collectorId || current.collector_id,
    approval: current.approval?.status === 'approved'
      ? { ...current.approval, status: 'none' }
      : current.approval,
  });
}

export function assertCircuitClosed(state) {
  if (state.circuit_open || state.consecutive_failures >= 3) {
    const err = new Error('circuit open: consecutive_failures >= 3; run factory heal or make reset');
    err.exitCode = EXIT.CIRCUIT;
    throw err;
  }
}

export function promotionBlocked(state) {
  if (!state) return false;
  if (state.status === 'PENDING_APPROVAL') return state.approval?.status !== 'approved';
  if (state.status === 'HEALING') return true;
  if (state.approval?.status === 'pending' || state.approval?.status === 'rejected') return true;
  return false;
}
