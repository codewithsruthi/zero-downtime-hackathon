import { createLogger } from '../logger.js';
import {
  resolveTraceContext,
  formatTraceparent,
  extractParentContextFromEnv,
  injectTraceparentIntoEnv,
} from './context.js';
import { increment, recordMs } from './metrics.js';
import { newTraceIds } from '../ids.js';

const log = createLogger();
const EXPORT_TIMEOUT_MS = 3000;
let exportFailLogged = false;
let sdkStarted = false;
let tracer = null;
let providerRef = null;
let apiMod = null;

function swallow(err) {
  if (!exportFailLogged) {
    log.warn('OTEL export failed; continuing', { error: err?.message || String(err) });
    exportFailLogged = true;
  }
}

async function getApi() {
  if (apiMod) return apiMod;
  try {
    apiMod = await import('@opentelemetry/api');
    return apiMod;
  } catch (err) {
    swallow(err);
    return null;
  }
}

export async function initOtel({ component = 'pipeline', env = process.env } = {}) {
  if (env.FACTORY_OTEL_DISABLED === '1' || !env.OTEL_EXPORTER_OTLP_ENDPOINT) {
    tracer = noopTracer();
    await getApi();
    return tracer;
  }
  if (sdkStarted && tracer) return tracer;
  try {
    const api = await getApi();
    if (!api) {
      tracer = noopTracer();
      return tracer;
    }
    const { NodeTracerProvider } = await import('@opentelemetry/sdk-trace-node');
    const { BatchSpanProcessor } = await import('@opentelemetry/sdk-trace-base');
    const { OTLPTraceExporter } = await import('@opentelemetry/exporter-trace-otlp-http');
    const { resourceFromAttributes } = await import('@opentelemetry/resources');
    const semconv = await import('@opentelemetry/semantic-conventions');
    const resource = resourceFromAttributes({
      [semconv.ATTR_SERVICE_NAME || 'service.name']: 'zero-downtime-factory',
      'factory.component': component,
    });
    const exporter = new OTLPTraceExporter({
      url: `${env.OTEL_EXPORTER_OTLP_ENDPOINT.replace(/\/$/, '')}/v1/traces`,
      headers: parseHeaders(env.OTEL_EXPORTER_OTLP_HEADERS),
      timeoutMillis: EXPORT_TIMEOUT_MS,
    });
    const provider = new NodeTracerProvider({
      resource,
      spanProcessors: [new BatchSpanProcessor(exporter, { scheduledDelayMillis: 200 })],
    });
    provider.register();
    providerRef = provider;
    const orig = exporter.export.bind(exporter);
    exporter.export = (spans, resultCallback) => {
      const timer = setTimeout(() => {
        swallow(new Error('OTLP export timed out after 3s'));
        try {
          resultCallback({ code: 0 });
        } catch {
          // ignore
        }
      }, EXPORT_TIMEOUT_MS);
      try {
        orig(spans, (res) => {
          clearTimeout(timer);
          if (res && res.code && res.code !== 0) swallow(res.error || new Error('OTLP export failed'));
          resultCallback(res);
        });
      } catch (err) {
        clearTimeout(timer);
        swallow(err);
        resultCallback({ code: 0 });
      }
    };
    tracer = api.trace.getTracer('zero-downtime-factory');
    sdkStarted = true;
    return tracer;
  } catch (err) {
    swallow(err);
    tracer = noopTracer();
    return tracer;
  }
}

function parseHeaders(raw) {
  if (!raw) return {};
  const headers = {};
  for (const part of raw.split(',')) {
    const idx = part.indexOf('=');
    if (idx > 0) headers[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
  }
  return headers;
}

function noopSpan() {
  return {
    setAttribute() {},
    addEvent() {},
    recordException() {},
    setStatus() {},
    end() {},
    spanContext() {
      return {
        traceId: '00000000000000000000000000000000',
        spanId: '0000000000000000',
        traceFlags: 0,
      };
    },
  };
}

function noopTracer() {
  return {
    startSpan() {
      return noopSpan();
    },
  };
}

function getTracer() {
  if (tracer) return tracer;
  if (apiMod) return apiMod.trace.getTracer('zero-downtime-factory');
  return noopTracer();
}

function parentContext(api, env) {
  if (!api) return undefined;
  if (api.trace.getSpan(api.context.active())) return api.context.active();
  return extractParentContextFromEnv(env);
}

async function runSpanBody(span, name, start, fn) {
  try {
    injectTraceparentIntoEnv(process.env);
  } catch (err) {
    swallow(err);
  }
  try {
    const result = await fn(span);
    span.end?.();
    recordMs('factory.span.ms', Date.now() - start, { name });
    return result;
  } catch (err) {
    try {
      span.recordException?.(err);
      span.addEvent?.('factory.failure', { message: err.message });
      span.end?.();
    } catch (inner) {
      swallow(inner);
    }
    recordMs('factory.span.ms', Date.now() - start, { name, error: true });
    throw err;
  }
}

export async function withSpan(name, attrs, fn) {
  const start = Date.now();
  increment('factory.spans', { name });
  const resolved = resolveTraceContext(process.env);
  const api = await getApi();
  const attributes = { ...attrs, 'factory.component': attrs?.['factory.component'] || 'pipeline' };
  let span;
  let parentCtx;
  try {
    parentCtx = parentContext(api, process.env);
    span = parentCtx !== undefined
      ? getTracer().startSpan(name, { attributes }, parentCtx)
      : getTracer().startSpan(name, { attributes });
    span.setAttribute?.('factory.trace_id', resolved.traceId);
  } catch (err) {
    swallow(err);
    span = noopSpan();
  }
  if (api && parentCtx !== undefined) {
    const spanCtx = api.trace.setSpan(parentCtx, span);
    return api.context.with(spanCtx, () => runSpanBody(span, name, start, fn));
  }
  return runSpanBody(span, name, start, fn);
}

export async function shutdown() {
  const provider = providerRef;
  providerRef = null;
  tracer = null;
  sdkStarted = false;
  if (!provider) return;
  try {
    await Promise.race([
      provider.shutdown(),
      new Promise((resolve) => setTimeout(resolve, EXPORT_TIMEOUT_MS)),
    ]);
  } catch (err) {
    swallow(err);
  }
}

export function currentTraceparent(env = process.env) {
  const ctx = resolveTraceContext(env);
  const ids = newTraceIds();
  return formatTraceparent({ traceId: ctx.traceId, spanId: ids.spanId, flags: ctx.flags });
}

export { EXPORT_TIMEOUT_MS };
