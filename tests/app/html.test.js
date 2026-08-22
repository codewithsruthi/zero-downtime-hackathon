import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { envelope, makeRoot, story, withServer } from '../helpers.js';

test('TEST-APP-01: GET / is HTML and lists story titles', async () => {
  const root = makeRoot();
  fs.writeFileSync(
    path.join(root, 'data', 'latest.json'),
    `${JSON.stringify(envelope([story({ title: 'Visible on the digest' })]), null, 2)}\n`,
  );
  await withServer(root, async ({ base }) => {
    const res = await fetch(`${base}/`);
    assert.equal(res.status, 200);
    assert.match(res.headers.get('content-type'), /html/);
    const body = await res.text();
    assert.match(body, /Visible on the digest/);
  });
});
