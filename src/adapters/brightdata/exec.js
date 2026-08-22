import { spawn } from 'node:child_process';
import fs from 'node:fs';
import { CLI } from './commands.js';
import { classify, extractFirstJson } from './classify.js';

const DEFAULT_TIMEOUT_MS = 120_000;

export function resolveOutput({ outPath, stdout }) {
  if (outPath && fs.existsSync(outPath)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(outPath, 'utf8'));
      return { parsed, source: 'file' };
    } catch {
      const extracted = extractFirstJson(fs.readFileSync(outPath, 'utf8'));
      if (extracted != null) return { parsed: extracted, source: 'file-extract' };
    }
  }
  const extracted = extractFirstJson(stdout || '');
  if (extracted != null) return { parsed: extracted, source: 'stdout' };
  return { parsed: null, source: null };
}

export function spawnCli({ args, env = process.env, timeoutMs = DEFAULT_TIMEOUT_MS, cwd }) {
  return new Promise((resolve) => {
    const child = spawn(CLI.bin, [...CLI.baseArgs, ...args], {
      env: { ...env, npm_config_update_notifier: 'false' },
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
    }, timeoutMs);
    child.stdout.on('data', (buf) => {
      stdout += buf.toString();
    });
    child.stderr.on('data', (buf) => {
      stderr += buf.toString();
    });
    child.on('error', (err) => {
      clearTimeout(timer);
      resolve({ exitCode: 1, stdout, stderr: `${stderr}\n${err.message}`, timedOut: false });
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ exitCode: timedOut ? null : code, stdout, stderr, timedOut });
    });
  });
}

export async function invoke({ args, outPath, env, timeoutMs, cwd }) {
  const spawned = await spawnCli({ args, env, timeoutMs, cwd });
  const resolved = resolveOutput({ outPath, stdout: spawned.stdout });
  const classified = classify({
    exitCode: spawned.exitCode,
    stdout: spawned.stdout,
    stderr: spawned.stderr,
    parsed: resolved.parsed,
    timedOut: spawned.timedOut,
  });
  return { ...spawned, ...resolved, ...classified, args };
}
