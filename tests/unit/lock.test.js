import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { tryAcquireLock, releaseLock } from '../../src/lock.js';
import { EXIT } from '../../src/config.js';

test('TEST-UNIT-04: second acquire fails while pid is live', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zdf-lock-'));
  const lockPath = path.join(dir, '.factory.lock');
  const first = tryAcquireLock(lockPath);
  assert.equal(first.ok, true);
  const second = tryAcquireLock(lockPath);
  assert.equal(second.ok, false);
  assert.equal(second.error.exitCode, EXIT.LOCK);
  releaseLock(lockPath);
  const third = tryAcquireLock(lockPath);
  assert.equal(third.ok, true);
  releaseLock(lockPath);
});

test('TEST-UNIT-04: dead pid is stolen', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zdf-lock-'));
  const lockPath = path.join(dir, '.factory.lock');
  fs.writeFileSync(lockPath, JSON.stringify({ pid: 999999, created_at: '2020-01-01T00:00:00.000Z' }));
  const stolen = tryAcquireLock(lockPath);
  assert.equal(stolen.ok, true);
  releaseLock(lockPath);
});
