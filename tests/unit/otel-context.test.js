import test from 'node:test';
import assert from 'node:assert/strict';
import { ROOT_CONTEXT, trace } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { InMemorySpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import {
  extractParentContextFromEnv,
  injectTraceparentIntoEnv,
  parseTraceparent,
} from '../../src/telemetry/context.js';
import { withSpan } from '../../src/telemetry/otel.js';
import { runCommand } from '../../src/commands/run.js';
import { factoryEnv, makeRoot } from '../helpers.js';

const TRACE_ID = 'a'.repeat(32);
const PARENT_SPAN_ID = 'b'.repeat(16);
const HEADER = `00-${TRACE_ID}-${PARENT_SPAN_ID}-01`;

test('TRACEPARENT extract continues the W3C parent context', () => {
  const ctx = extractParentContextFromEnv({ TRACEPARENT: HEADER });
  const sc = trace.getSpanContext(ctx);
  assert.ok(sc);
  assert.equal(sc.traceId, TRACE_ID);
  assert.equal(sc.spanId, PARENT_SPAN_ID);
});

test('TRACEPARENT extract is ROOT when unset', () => {
  const ctx = extractParentContextFromEnv({});
  assert.equal(ctx, ROOT_CONTEXT);
  assert.equal(trace.getSpan(ctx), undefined);
});

test('TRACEPARENT inject writes the active span into env', () => {
  const childSpanId = 'c'.repeat(16);
  const parent = trace.setSpanContext(ROOT_CONTEXT, {
    traceId: TRACE_ID,
    spanId: childSpanId,
    traceFlags: 1,
  });
  const env = {};
  injectTraceparentIntoEnv(env, parent);
  assert.equal(env.TRACEPARENT, `00-${TRACE_ID}-${childSpanId}-01`);
});

test('TRACEPARENT inject leaves env alone without an active span', () => {
  const env = { TRACEPARENT: HEADER };
  injectTraceparentIntoEnv(env);
  assert.equal(env.TRACEPARENT, HEADER);
});

async function withMemoryProvider(fn) {
  const exporter = new InMemorySpanExporter();
  const provider = new NodeTracerProvider({
    spanProcessors: [new SimpleSpanProcessor(exporter)],
  });
  provider.register();
  const prev = process.env.TRACEPARENT;
  try {
    return await fn({ exporter, provider });
  } finally {
    if (prev === undefined) delete process.env.TRACEPARENT;
    else process.env.TRACEPARENT = prev;
    await provider.shutdown();
    trace.disable();
  }
}

test('withSpan parents the root span on TRACEPARENT', async () => {
  await withMemoryProvider(async ({ exporter }) => {
    process.env.TRACEPARENT = HEADER;
    await withSpan('factory.run', { 'factory.component': 'pipeline' }, async () => {
      await withSpan('factory.scrape', { 'factory.component': 'pipeline' }, async () => {});
    });
    const spans = exporter.getFinishedSpans();
    const run = spans.find((s) => s.name === 'factory.run');
    const scrape = spans.find((s) => s.name === 'factory.scrape');
    assert.ok(run, 'factory.run span exported');
    assert.ok(scrape, 'factory.scrape span exported');
    assert.equal(run.spanContext().traceId, TRACE_ID);
    assert.equal(scrape.spanContext().traceId, TRACE_ID);
    assert.equal(run.parentSpanId, PARENT_SPAN_ID);
    assert.equal(scrape.parentSpanId, run.spanContext().spanId);
  });
});

test('factory run injects TRACEPARENT for child commands', async () => {
  await withMemoryProvider(async () => {
    process.env.TRACEPARENT = HEADER;
    const root = makeRoot();
    const env = factoryEnv(root, { TRACEPARENT: HEADER });
    const result = await runCommand({
      root,
      flags: { dryRun: true },
      env,
      log: { info() {}, error() {}, warn() {} },
    });
    assert.equal(result.exitCode, 0);
    const injected = parseTraceparent(env.TRACEPARENT);
    assert.ok(injected);
    assert.equal(injected.traceId, TRACE_ID);
    assert.notEqual(injected.parentSpanId, PARENT_SPAN_ID);
  });
});
