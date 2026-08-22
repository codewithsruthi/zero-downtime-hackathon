import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { factoryEnv, makeRoot, runFactoryBin } from '../helpers.js';

test('TEST-INT-05: reject blocks promote; rollback restores a snapshot', async () => {
  const root = makeRoot();
  const env = factoryEnv(root);
  assert.equal((await runFactoryBin(['run', '--json'], env)).code, 0);
  const first = JSON.parse(fs.readFileSync(path.join(root, 'data', 'latest.json'), 'utf8'));
  assert.equal((await runFactoryBin(['break', '--json'], env)).code, 0);
  await runFactoryBin(['scrape', '--json'], env);
  assert.equal((await runFactoryBin(['heal', '--json'], env)).code, 0);
  assert.equal((await runFactoryBin(['reject', '--json'], env)).code, 0);
  const blocked = await runFactoryBin(['promote', '--json'], env);
  assert.equal(blocked.code, 8);
  const still = JSON.parse(fs.readFileSync(path.join(root, 'data', 'latest.json'), 'utf8'));
  assert.equal(still.run_id, first.run_id);

  fs.writeFileSync(
    path.join(root, 'data', 'candidate.json'),
    JSON.stringify({ ...first, run_id: 'run-second', stories: first.stories.map((s, i) => (i === 0 ? { ...s, title: 'Changed' } : s)) }, null, 2),
  );
  const statePath = path.join(root, 'data', 'state.json');
  const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
  state.status = 'HEALTHY';
  state.approval = { id: null, status: 'none', requested_at: null, resolved_at: null };
  fs.writeFileSync(statePath, JSON.stringify(state, null, 2));
  assert.equal((await runFactoryBin(['promote', '--json'], env)).code, 0);
  const rolled = await runFactoryBin(['rollback', '--json'], env);
  assert.equal(rolled.code, 0, rolled.stderr);
  const restored = JSON.parse(fs.readFileSync(path.join(root, 'data', 'latest.json'), 'utf8'));
  assert.equal(restored.run_id, first.run_id);
});
