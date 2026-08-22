import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { REPO } from '../helpers.js';

test('TEST-DEMO-01: demo.sh in replay exits 0', async () => {
  const env = {
    ...process.env,
    FACTORY_MODE: 'replay',
    FACTORY_OTEL_DISABLED: '1',
    FACTORY_APP_PORT: String(34000 + Math.floor(Math.random() * 1000)),
    FACTORY_COLLECTOR_ID: 'c_hn_digest_factory',
  };
  const result = await new Promise((resolve) => {
    const child = spawn('bash', [path.join(REPO, 'scripts', 'demo.sh')], {
      env,
      cwd: REPO,
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => child.kill('SIGTERM'), 40000);
    child.stdout.on('data', (b) => {
      stdout += b.toString();
    });
    child.stderr.on('data', (b) => {
      stderr += b.toString();
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code, stdout, stderr });
    });
  });
  assert.equal(result.code, 0, result.stderr + result.stdout);
  assert.match(result.stdout, /DEMO_OK/);
});
