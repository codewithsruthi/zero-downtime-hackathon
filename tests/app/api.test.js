import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { envelope, makeRoot, story, withServer } from '../helpers.js';

test('TEST-APP-02: /api/stories and /api/health return JSON', async () => {
  const root = makeRoot();
  fs.writeFileSync(
    path.join(root, 'data', 'latest.json'),
    `${JSON.stringify(envelope([story({ title: 'API story' })]), null, 2)}\n`,
  );
  await withServer(root, async ({ base }) => {
    const stories = await fetch(`${base}/api/stories`);
    assert.equal(stories.status, 200);
    const sjson = await stories.json();
    assert.equal(sjson.stories[0].title, 'API story');
    const health = await fetch(`${base}/api/health`);
    assert.equal(health.status, 200);
    const hjson = await health.json();
    assert.equal(hjson.story_count, 1);
    assert.ok(hjson.factory_status);
  });
});
