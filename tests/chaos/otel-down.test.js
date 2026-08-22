import test from 'node:test';
import assert from 'node:assert/strict';
import { factoryEnv, makeRoot, runFactoryBin } from '../helpers.js';

test('TEST-CHAOS-03: bad OTLP endpoint does not fail the pipeline', async () => {
  const root = makeRoot();
  const env = factoryEnv(root, {
    FACTORY_OTEL_DISABLED: '',
    OTEL_EXPORTER_OTLP_ENDPOINT: 'http://127.0.0.1:1',
  });
  const run = await runFactoryBin(['run', '--json'], env);
  assert.equal(run.code, 0, run.stderr);
});
