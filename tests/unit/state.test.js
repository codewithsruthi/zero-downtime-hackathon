import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { EXIT } from '../../src/config.js';
import {
  emptyState,
  isLegalTransition,
  loadState,
  recordFailure,
  saveState,
  transition,
} from '../../src/state.js';
import { makeRoot } from '../helpers.js';
import { envelope, story } from '../helpers.js';

test('TEST-UNIT-06: illegal transition throws exit 3', () => {
  const root = makeRoot();
  saveState({ ...emptyState(), status: 'HEALTHY' }, root);
  assert.throws(
    () => transition(root, 'PENDING_APPROVAL'),
    (err) => err.exitCode === EXIT.ILLEGAL_TRANSITION,
  );
  assert.equal(isLegalTransition('BROKEN', 'HEALTHY'), false);
  assert.equal(isLegalTransition('BROKEN', 'HEALING'), true);
});

test('TEST-UNIT-06: reconstruct HEALTHY from latest.json (EC-SM-02)', () => {
  const root = makeRoot();
  fs.writeFileSync(
    path.join(root, 'data', 'latest.json'),
    JSON.stringify(envelope([story()]), null, 2),
  );
  const state = loadState(root);
  assert.equal(state.status, 'HEALTHY');
  assert.equal(state.consecutive_failures, 0);
});

test('TEST-UNIT-06: reconstruct UNKNOWN when latest is absent', () => {
  const root = makeRoot();
  const state = loadState(root);
  assert.equal(state.status, 'UNKNOWN');
});

test('TEST-UNIT-06: circuit opens at 3 consecutive failures (EC-SM-03)', () => {
  const root = makeRoot();
  saveState({ ...emptyState(), status: 'HEALTHY' }, root);
  recordFailure(root, 'fail-1');
  recordFailure(root, 'fail-2');
  const third = recordFailure(root, 'fail-3');
  assert.equal(third.consecutive_failures, 3);
  assert.equal(third.circuit_open, true);
  assert.equal(third.status, 'BROKEN');
});
