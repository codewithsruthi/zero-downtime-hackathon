import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..');

export const EXIT = {
  SUCCESS: 0,
  GENERIC: 1,
  CONFIG: 2,
  ILLEGAL_TRANSITION: 3,
  VALIDATION: 4,
  SCRAPE: 5,
  LOCK: 6,
  CIRCUIT: 7,
  NOT_APPROVED: 8,
  HEAL: 9,
  PARSE: 10,
  FILE: 11,
  USAGE: 12,
};

export const DEFAULT_COLLECTOR_ID = 'c_hn_digest_factory';
export const DEFAULT_HN_URL = 'https://news.ycombinator.com';
export const PINNED_CLI = '@brightdata/cli@0.3.5';

export function getRoot(env = process.env) {
  return env.FACTORY_ROOT ? path.resolve(env.FACTORY_ROOT) : REPO_ROOT;
}

export function paths(root = getRoot()) {
  return {
    root,
    data: path.join(root, 'data'),
    raw: path.join(root, 'data', 'raw'),
    snapshots: path.join(root, 'data', 'snapshots'),
    sample: path.join(root, 'data', 'sample-output'),
    latest: path.join(root, 'data', 'latest.json'),
    candidate: path.join(root, 'data', 'candidate.json'),
    state: path.join(root, 'data', 'state.json'),
    lock: path.join(root, 'data', '.factory.lock'),
    brokenMarker: path.join(root, 'data', '.broken'),
    healedMarker: path.join(root, 'data', '.healed'),
    ledger: path.join(root, 'port', 'state', 'ledger.jsonl'),
    claude: path.join(root, 'CLAUDE.md'),
    scraperRules: path.join(root, 'agent-rules', 'scraper.md'),
    collectors: path.join(root, 'data', 'collectors.md'),
  };
}

export function ensureDataDirs(root = getRoot()) {
  const p = paths(root);
  for (const dir of [p.data, p.raw, p.snapshots, p.sample, path.dirname(p.ledger)]) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return p;
}

export function loadDotEnv(root = getRoot(), env = process.env) {
  const file = path.join(root, '.env');
  if (!fs.existsSync(file)) return env;
  const text = fs.readFileSync(file, 'utf8');
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq < 1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (env[key] === undefined) env[key] = value;
  }
  return env;
}

export function configError(name, detail) {
  const err = new Error(`Missing or invalid ${name}${detail ? `: ${detail}` : ''}`);
  err.exitCode = EXIT.CONFIG;
  err.varName = name;
  return err;
}

export function getMode(env = process.env) {
  const mode = (env.FACTORY_MODE || 'replay').toLowerCase();
  if (!['live', 'record', 'replay'].includes(mode)) {
    throw configError('FACTORY_MODE', `expected live|record|replay, got ${mode}`);
  }
  return mode;
}

export function extractCollectorId(text) {
  if (!text) return null;
  const m = text.match(/SCRAPER_STUDIO_COLLECTOR_ID\s*=\s*([A-Za-z0-9_]+)/);
  if (m) return m[1];
  const m2 = text.match(/FACTORY_COLLECTOR_ID\s*=\s*([A-Za-z0-9_]+)/);
  return m2 ? m2[1] : null;
}

export function resolveCollectorId({ flag, root = getRoot(), env = process.env } = {}) {
  if (flag) return flag;
  if (env.FACTORY_COLLECTOR_ID) return env.FACTORY_COLLECTOR_ID;
  if (env.BRIGHTDATA_COLLECTOR_ID) return env.BRIGHTDATA_COLLECTOR_ID;
  const p = paths(root);
  if (fs.existsSync(p.claude)) {
    const id = extractCollectorId(fs.readFileSync(p.claude, 'utf8'));
    if (id) return id;
  }
  if (fs.existsSync(p.scraperRules)) {
    const id = extractCollectorId(fs.readFileSync(p.scraperRules, 'utf8'));
    if (id) return id;
  }
  throw configError(
    'FACTORY_COLLECTOR_ID',
    'set --collector-id, FACTORY_COLLECTOR_ID, BRIGHTDATA_COLLECTOR_ID, or SCRAPER_STUDIO_COLLECTOR_ID in CLAUDE.md / agent-rules/scraper.md',
  );
}

export function requireLiveKey(env = process.env) {
  if (getMode(env) === 'live' && !env.BRIGHTDATA_API_KEY) {
    throw configError('BRIGHTDATA_API_KEY', 'required when FACTORY_MODE=live');
  }
}

export function getHnUrl(env = process.env) {
  return env.FACTORY_HN_URL || DEFAULT_HN_URL;
}

export function getAppPort(env = process.env) {
  return Number(env.FACTORY_APP_PORT || env.PORT || 3000);
}
