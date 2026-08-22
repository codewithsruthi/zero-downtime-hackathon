import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { factoryEnv, makeRoot, runFactoryBin } from '../helpers.js';

test('TEST-INT-04: remote Port failure still writes the ledger and exits 0', async () => {
  const root = makeRoot();
  const env = factoryEnv(root, {
    PORT_API_URL: 'http://127.0.0.1:1',
    PORT_CLIENT_ID: 'x',
    PORT_CLIENT_SECRET: 'y',
  });
  const scrape = await runFactoryBin(['scrape', '--json'], env);
  assert.equal(scrape.code, 0, scrape.stderr);
  const sync = await runFactoryBin(['port-sync', '--json'], env);
  assert.equal(sync.code, 0, sync.stderr);
  const ledgerPath = path.join(root, 'port', 'state', 'ledger.jsonl');
  assert.equal(fs.existsSync(ledgerPath), true);
  const lines = fs.readFileSync(ledgerPath, 'utf8').trim().split('\n');
  assert.ok(lines.length >= 1);
  const last = JSON.parse(lines[lines.length - 1]);
  assert.equal(last.remote_ok, false);
  assert.ok(last.type);
});
