import { context, propagation, ROOT_CONTEXT, trace } from '@opentelemetry/api';
import { W3CTraceContextPropagator } from '@opentelemetry/core';
import { newTraceIds } from '../ids.js';

let propagatorReady = false;

export function ensurePropagator() {
  if (propagatorReady) return;
  propagation.setGlobalPropagator(new W3CTraceContextPropagator());
  propagatorReady = true;
}

export function parseTraceparent(header) {
  if (!header || typeof header !== 'string') return null;
  const parts = header.trim().split('-');
  if (parts.length !== 4) return null;
  const [version, traceId, parentSpanId, flags] = parts;
  if (traceId.length !== 32 || parentSpanId.length !== 16) return null;
  return { version, traceId, parentSpanId, flags };
}

export function formatTraceparent({ traceId, spanId, flags = '01' }) {
  return `00-${traceId}-${spanId}-${flags}`;
}

export function resolveTraceContext(env = process.env) {
  const parsed = parseTraceparent(env.TRACEPARENT);
  if (parsed) {
    return {
      traceId: parsed.traceId,
      parentSpanId: parsed.parentSpanId,
      flags: parsed.flags,
      source: 'env',
    };
  }
  const ids = newTraceIds();
  return { traceId: ids.traceId, parentSpanId: null, flags: '01', source: 'new' };
}

export function childTraceparent(ctx, spanId) {
  return formatTraceparent({ traceId: ctx.traceId, spanId, flags: ctx.flags || '01' });
}

export function extractParentContextFromEnv(env = process.env) {
  ensurePropagator();
  const header = env?.TRACEPARENT;
  if (!header) return ROOT_CONTEXT;
  return propagation.extract(ROOT_CONTEXT, { traceparent: header });
}

export function injectTraceparentIntoEnv(env = process.env, ctx = context.active()) {
  ensurePropagator();
  const sc = trace.getSpanContext(ctx);
  if (!sc || !trace.isSpanContextValid(sc)) return env.TRACEPARENT;
  const carrier = {};
  propagation.inject(ctx, carrier);
  if (carrier.traceparent) env.TRACEPARENT = carrier.traceparent;
  return env.TRACEPARENT;
}
