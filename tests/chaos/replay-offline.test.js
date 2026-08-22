import test from 'node:test';
import assert from 'node:assert/strict';
import { factoryEnv, makeRoot, runFactoryBin } from '../helpers.js';

test('TEST-CHAOS-05: replay scrape works without a usable network PATH', async () => {
  const root = makeRoot();
  const env = factoryEnv(root, {
    PATH: '/tmp/no-such-factory-bin',
    http_proxy: 'http://127.0.0.1:1',
    https_proxy: 'http://127.0.0.1:1',
    HTTP_PROXY: 'http://127.0.0.1:1',
    HTTPS_PROXY: 'http://127.0.0.1:1',
    NO_PROXY: '*',
  });
  const scrape = await runFactoryBin(['scrape', '--json'], env);
  assert.equal(scrape.code, 0, scrape.stderr);
});
