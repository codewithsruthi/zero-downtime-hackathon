import test from 'node:test';
import assert from 'node:assert/strict';
import { makeRoot, withServer } from '../helpers.js';

test('TEST-CHAOS-02: app returns 200 with no latest.json', async () => {
  const root = makeRoot();
  await withServer(root, async ({ base }) => {
    const html = await fetch(`${base}/`);
    assert.equal(html.status, 200);
    const body = await html.text();
    assert.match(body, /digest/i);
    const health = await fetch(`${base}/api/health`);
    assert.equal(health.status, 200);
    const json = await health.json();
    assert.ok(['waiting', 'ok', 'degraded'].includes(json.status));
  });
});
