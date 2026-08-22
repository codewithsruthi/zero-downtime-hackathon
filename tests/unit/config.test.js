import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { extractCollectorId, resolveCollectorId } from '../../src/config.js';

test('TEST-UNIT-05: collector id precedence flag > env > CLAUDE.md > agent-rules', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zdf-cfg-'));
  fs.mkdirSync(path.join(dir, 'agent-rules'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'agent-rules', 'scraper.md'), 'SCRAPER_STUDIO_COLLECTOR_ID=c_from_rules\n');
  assert.equal(resolveCollectorId({ flag: 'c_flag', root: dir, env: {} }), 'c_flag');
  assert.equal(
    resolveCollectorId({ root: dir, env: { FACTORY_COLLECTOR_ID: 'c_factory' } }),
    'c_factory',
  );
  assert.equal(
    resolveCollectorId({ root: dir, env: { BRIGHTDATA_COLLECTOR_ID: 'c_bd' } }),
    'c_bd',
  );
  fs.writeFileSync(path.join(dir, 'CLAUDE.md'), 'SCRAPER_STUDIO_COLLECTOR_ID=c_from_claude\n');
  assert.equal(resolveCollectorId({ root: dir, env: {} }), 'c_from_claude');
  fs.unlinkSync(path.join(dir, 'CLAUDE.md'));
  assert.equal(resolveCollectorId({ root: dir, env: {} }), 'c_from_rules');
});

test('TEST-UNIT-05: extractCollectorId reads the rules key', () => {
  assert.equal(extractCollectorId('SCRAPER_STUDIO_COLLECTOR_ID=c_hn_digest_factory\n'), 'c_hn_digest_factory');
});
