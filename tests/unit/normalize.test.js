import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalize } from '../../src/pipeline/normalize.js';

const RAW = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures', 'raw');

test('TEST-UNIT-02: N-01 nested hits unwrap', () => {
  const raw = JSON.parse(fs.readFileSync(path.join(RAW, 'nested-hits.json'), 'utf8'));
  const doc = normalize(raw, { collectorId: 'c_hn_digest_factory', runId: 'run-n', generatedAt: '2026-08-21T12:00:00.000Z' });
  assert.equal(doc.stories.length, 2);
  assert.equal(doc.stories[0].title, 'Nested');
  assert.equal(doc.stories[0].url, 'https://nested.example/a');
});

test('TEST-UNIT-02: N-04/N-05 coerce string numbers', () => {
  const raw = JSON.parse(fs.readFileSync(path.join(RAW, 'string-points.json'), 'utf8'));
  const doc = normalize(raw, { collectorId: 'c_x', runId: 'run-s', generatedAt: '2026-08-21T12:00:00.000Z' });
  assert.equal(doc.stories[0].points, 99);
  assert.equal(doc.stories[0].comment_count, 4);
  assert.equal(doc.stories[0].author, 'carol');
});

test('TEST-UNIT-02: N-09 job posts flagged and kept', () => {
  const raw = JSON.parse(fs.readFileSync(path.join(RAW, 'job-raw.json'), 'utf8'));
  const doc = normalize(raw, { collectorId: 'c_x', runId: 'run-j', generatedAt: '2026-08-21T12:00:00.000Z' });
  assert.equal(doc.stories[0].is_job, true);
  assert.ok(doc.stories[0].title.includes('hiring'));
});

test('TEST-UNIT-02: N-10 dedupe keeps higher points', () => {
  const raw = [
    { title: 'A', url: 'https://dup.example/a', points: 1 },
    { title: 'A2', url: 'https://dup.example/a', points: 9 },
  ];
  const doc = normalize(raw, { collectorId: 'c', runId: 'r', generatedAt: '2026-08-21T12:00:00.000Z' });
  assert.equal(doc.stories.length, 1);
  assert.equal(doc.stories[0].points, 9);
  assert.equal(doc.story_count, 1);
});

test('TEST-UNIT-02: N-11 caps at 30 and assigns rank', () => {
  const raw = Array.from({ length: 40 }, (_, i) => ({
    title: `T${i}`,
    url: `https://n.example/${i}`,
    points: i,
  }));
  const doc = normalize(raw, { collectorId: 'c', runId: 'r', generatedAt: '2026-08-21T12:00:00.000Z' });
  assert.equal(doc.stories.length, 30);
  assert.equal(doc.stories[0].rank, 1);
  assert.equal(doc.stories[29].rank, 30);
});
