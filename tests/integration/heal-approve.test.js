import test from 'node:test';
import assert from 'node:assert/strict';
import { factoryEnv, makeRoot, runFactoryBin } from '../helpers.js';

test('TEST-INT-03: heal → pending → approve → re-run keeps the same collector id', async () => {
  const root = makeRoot();
  const env = factoryEnv(root);
  assert.equal((await runFactoryBin(['run', '--json'], env)).code, 0);
  assert.equal((await runFactoryBin(['break', '--json'], env)).code, 0);
  const broken = await runFactoryBin(['scrape', '--json'], env);
  assert.notEqual(broken.code, 0);
  const heal = await runFactoryBin(['heal', '--json'], env);
  assert.equal(heal.code, 0, heal.stderr);
  const healBody = JSON.parse(heal.stdout);
  assert.equal(healBody.result.state.status, 'PENDING_APPROVAL');
  const blocked = await runFactoryBin(['promote', '--json'], env);
  assert.equal(blocked.code, 8);
  const approve = await runFactoryBin(['approve', '--json'], env);
  assert.equal(approve.code, 0, approve.stderr);
  const rerun = await runFactoryBin(['run', '--json'], env);
  assert.equal(rerun.code, 0, rerun.stderr);
  const rerunBody = JSON.parse(rerun.stdout);
  const collector = rerunBody.result.candidate?.collector_id || rerunBody.result.doc?.collector_id;
  assert.equal(healBody.result.collectorId, 'c_hn_digest_factory');
  assert.equal(collector, 'c_hn_digest_factory');
});
