import test from 'node:test';
import assert from 'node:assert/strict';
import { factoryEnv, makeRoot, runFactoryBin } from '../helpers.js';

test('TEST-CHAOS-01: factory break then scrape fails', async () => {
  const root = makeRoot();
  const env = factoryEnv(root);
  assert.equal((await runFactoryBin(['run', '--json'], env)).code, 0);
  assert.equal((await runFactoryBin(['break', '--json'], env)).code, 0);
  const scrape = await runFactoryBin(['scrape', '--json'], env);
  assert.notEqual(scrape.code, 0);
});
