import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { atomicWriteFile, atomicWriteJson } from '../../src/atomic.js';

test('TEST-UNIT-03: atomic write replaces via rename', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zdf-atomic-'));
  const dest = path.join(dir, 'latest.json');
  atomicWriteFile(dest, '{"ok":true}\n');
  assert.equal(fs.readFileSync(dest, 'utf8'), '{"ok":true}\n');
  atomicWriteJson(dest, { ok: false, n: 2 });
  const parsed = JSON.parse(fs.readFileSync(dest, 'utf8'));
  assert.deepEqual(parsed, { ok: false, n: 2 });
  const leftovers = fs.readdirSync(dir).filter((f) => f.includes('.tmp'));
  assert.deepEqual(leftovers, []);
});

test('TEST-UNIT-03: planted tmp file is not promoted to latest', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zdf-atomic-'));
  const dest = path.join(dir, 'latest.json');
  fs.writeFileSync(dest, '{"good":true}\n');
  fs.writeFileSync(path.join(dir, '.latest.json.999.tmp'), '{"partial":true}\n');
  atomicWriteJson(dest, { good: true, v: 2 });
  const parsed = JSON.parse(fs.readFileSync(dest, 'utf8'));
  assert.equal(parsed.good, true);
  assert.equal(parsed.v, 2);
  assert.notEqual(parsed.partial, true);
});
