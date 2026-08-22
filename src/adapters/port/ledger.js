import fs from 'node:fs';
import path from 'node:path';
import { paths, ensureDataDirs } from '../../config.js';

export function appendLedger(root, entry) {
  const p = ensureDataDirs(root);
  fs.mkdirSync(path.dirname(p.ledger), { recursive: true });
  const line = {
    ts: new Date().toISOString(),
    remote_ok: false,
    remote_error: null,
    ...entry,
  };
  fs.appendFileSync(p.ledger, `${JSON.stringify(line)}\n`);
  return line;
}

export function readLedger(root) {
  const p = paths(root);
  if (!fs.existsSync(p.ledger)) return [];
  return fs
    .readFileSync(p.ledger, 'utf8')
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

export function rewriteLedger(root, entries) {
  const p = ensureDataDirs(root);
  const text = entries.map((e) => JSON.stringify(e)).join('\n');
  fs.writeFileSync(p.ledger, text ? `${text}\n` : '');
}
