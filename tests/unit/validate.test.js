import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validate, failedGateIds } from '../../src/pipeline/validate.js';

const FIX = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
const verdicts = JSON.parse(fs.readFileSync(path.join(FIX, 'verdicts.json'), 'utf8'));

test('TEST-UNIT-01: all 14 fixtures match documented verdicts', () => {
  const names = Object.keys(verdicts).sort();
  assert.equal(names.length, 14);
  for (const name of names) {
    const expected = verdicts[name];
    const raw = JSON.parse(fs.readFileSync(path.join(FIX, name), 'utf8'));
    const report = validate(raw);
    assert.equal(report.ok, expected.ok, `${name} ok`);
    assert.deepEqual(failedGateIds(report), expected.failed, `${name} failed gates`);
  }
});

test('TEST-UNIT-01: job posts PASS (EC-DATA-01)', () => {
  const doc = JSON.parse(fs.readFileSync(path.join(FIX, '02-job-posts.json'), 'utf8'));
  const report = validate(doc);
  assert.equal(report.ok, true);
  assert.equal(doc.stories[0].is_job, true);
});

test('REQ-VAL-01: validate is pure and does not throw on garbage', () => {
  assert.equal(validate(null).ok, false);
  assert.equal(validate('nope').ok, false);
  assert.equal(validate(42).ok, false);
});
