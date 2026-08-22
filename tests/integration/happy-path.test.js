import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { factoryEnv, makeRoot, runFactoryBin } from '../helpers.js';
import { validate } from '../../src/pipeline/validate.js';

test('TEST-INT-01: replay scrape → validate → promote writes valid latest.json', async () => {
  const root = makeRoot();
  const env = factoryEnv(root);
  const scrape = await runFactoryBin(['scrape', '--json'], env);
  assert.equal(scrape.code, 0, scrape.stderr);
  const promote = await runFactoryBin(['promote', '--json'], env);
  assert.equal(promote.code, 0, promote.stderr);
  const latest = JSON.parse(fs.readFileSync(path.join(root, 'data', 'latest.json'), 'utf8'));
  assert.equal(validate(latest).ok, true);
  assert.ok(latest.stories.length >= 1);
  assert.equal(latest.collector_id, 'c_hn_digest_factory');
});
