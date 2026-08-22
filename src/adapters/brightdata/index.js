import fs from 'node:fs';
import path from 'node:path';
import { CLI } from './commands.js';
import { invoke } from './exec.js';
import { EXIT, getMode, paths, ensureDataDirs } from '../../config.js';
import { atomicWriteJson } from '../../atomic.js';

function replayFile(root, name) {
  return path.join(paths(root).sample, name);
}

function readReplay(root, name) {
  const file = replayFile(root, name);
  if (!fs.existsSync(file)) {
    const err = new Error(`replay fixture missing: ${file}`);
    err.exitCode = EXIT.FILE;
    throw err;
  }
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function writeRaw(root, runId, payload) {
  const p = ensureDataDirs(root);
  const outPath = path.join(p.raw, `run-${runId}.json`);
  atomicWriteJson(outPath, payload);
  return outPath;
}

export async function runScraper({ root, collectorId, url, runId, env = process.env }) {
  const mode = getMode(env);
  const p = ensureDataDirs(root);
  const outPath = path.join(p.raw, `run-${runId}.json`);

  if (mode === 'replay') {
    const name = fs.existsSync(p.brokenMarker)
      ? 'broken.json'
      : fs.existsSync(p.healedMarker)
        ? 'healed.json'
        : 'healthy.json';
    const payload = readReplay(root, name);
    writeRaw(root, runId, payload);
    const ok = name !== 'broken.json';
    return {
      code: ok ? 'OK' : 'FAIL_PARSE',
      parsed: payload,
      outPath,
      mode,
      collectorId,
    };
  }

  const args = CLI.run({ collectorId, url, outPath });
  const result = await invoke({ args, outPath, env });
  if (result.parsed != null) {
    writeRaw(root, runId, result.parsed);
  }
  if (mode === 'record' && result.parsed != null) {
    atomicWriteJson(replayFile(root, 'healthy.json'), result.parsed);
  }
  return { ...result, outPath, mode, collectorId };
}

export async function healScraper({ root, collectorId, url, prompt, env = process.env }) {
  const mode = getMode(env);
  if (mode === 'replay') {
    const preview = readReplay(root, 'heal-preview.json');
    return { code: 'OK', parsed: preview, mode, collectorId };
  }
  const args = CLI.heal({ collectorId, prompt, url });
  return { ...(await invoke({ args, env })), mode, collectorId };
}

export async function approveScraper({ root, collectorId, url, env = process.env }) {
  const mode = getMode(env);
  if (mode === 'replay') {
    return { code: 'OK', parsed: { status: 'done', collector_id: collectorId }, mode, collectorId };
  }
  const args = CLI.approve({ collectorId, url });
  return { ...(await invoke({ args, env })), mode, collectorId };
}

export async function rejectScraper({ collectorId, env = process.env }) {
  const mode = getMode(env);
  if (mode === 'replay') {
    return { code: 'OK', parsed: { status: 'rejected', collector_id: collectorId }, mode, collectorId };
  }
  const args = CLI.reject({ collectorId });
  return { ...(await invoke({ args, env })), mode, collectorId };
}

export { CLI };
