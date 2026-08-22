import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function envelope(stories, extra = {}) {
  return {
    schema_version: 1,
    generated_at: extra.generated_at || '2026-08-21T12:00:00.000Z',
    source: extra.source === undefined ? 'https://news.ycombinator.com' : extra.source,
    collector_id: extra.collector_id === undefined ? 'c_hn_digest_factory' : extra.collector_id,
    run_id: extra.run_id === undefined ? 'run-test-1' : extra.run_id,
    story_count: stories.length,
    stories,
  };
}

export function story(partial = {}) {
  return {
    id: 'hn-1',
    rank: 1,
    title: 'Example story',
    url: 'https://example.com/story',
    site: 'example.com',
    points: 10,
    comment_count: 2,
    author: 'pg',
    age: '1 hour ago',
    is_job: false,
    ...partial,
  };
}

export function makeRoot() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zdf-'));
  for (const sub of ['data/raw', 'data/snapshots', 'data/sample-output', 'port/state', 'agent-rules']) {
    fs.mkdirSync(path.join(dir, sub), { recursive: true });
  }
  const sampleSrc = path.join(REPO, 'data', 'sample-output');
  for (const file of fs.readdirSync(sampleSrc)) {
    fs.copyFileSync(path.join(sampleSrc, file), path.join(dir, 'data', 'sample-output', file));
  }
  fs.writeFileSync(
    path.join(dir, 'CLAUDE.md'),
    'SCRAPER_STUDIO_COLLECTOR_ID=c_hn_digest_factory\n',
  );
  fs.writeFileSync(
    path.join(dir, 'agent-rules', 'scraper.md'),
    'SCRAPER_STUDIO_COLLECTOR_ID=c_hn_digest_factory\n',
  );
  return dir;
}

export function factoryEnv(root, extra = {}) {
  return {
    ...process.env,
    FACTORY_ROOT: root,
    FACTORY_MODE: 'replay',
    FACTORY_OTEL_DISABLED: '1',
    FACTORY_COLLECTOR_ID: 'c_hn_digest_factory',
    ...extra,
  };
}

export function runFactoryBin(args, env, timeoutMs = 20000) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [path.join(REPO, 'bin', 'factory'), ...args], {
      env,
      cwd: REPO,
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
    }, timeoutMs);
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
}

export async function withServer(root, fn) {
  const { startServer } = await import('../app/server.js');
  const { server, port } = await startServer({ root, port: 0 });
  const address = server.address();
  const actualPort = typeof address === 'object' ? address.port : port;
  try {
    return await fn({ port: actualPort, base: `http://127.0.0.1:${actualPort}` });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}
