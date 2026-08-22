import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { makeRoot, withServer } from '../helpers.js';

test('TEST-CHAOS-04: corrupt latest.json still serves 200 with degraded health', async () => {
  const root = makeRoot();
  fs.writeFileSync(path.join(root, 'data', 'latest.json'), '{not-json');
  await withServer(root, async ({ base }) => {
    const html = await fetch(`${base}/`);
    assert.equal(html.status, 200);
    const health = await fetch(`${base}/api/health`);
    assert.equal(health.status, 200);
    const json = await health.json();
    assert.equal(json.status, 'degraded');
  });
});
