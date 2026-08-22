import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { envelope, factoryEnv, makeRoot, runFactoryBin, story } from '../helpers.js';

test('TEST-INT-02: failed scrape leaves latest.json untouched', async () => {
  const root = makeRoot();
  const env = factoryEnv(root);
  const original = envelope([story({ title: 'Keep me' })]);
  fs.writeFileSync(path.join(root, 'data', 'latest.json'), `${JSON.stringify(original, null, 2)}\n`);
  fs.writeFileSync(path.join(root, 'data', '.broken'), 'yes\n');
  const scrape = await runFactoryBin(['scrape', '--json'], env);
  assert.notEqual(scrape.code, 0);
  const after = JSON.parse(fs.readFileSync(path.join(root, 'data', 'latest.json'), 'utf8'));
  assert.equal(after.stories[0].title, 'Keep me');
  assert.equal(after.run_id, original.run_id);
});
