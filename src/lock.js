import fs from 'node:fs';
import path from 'node:path';
import { EXIT } from './config.js';

function pidAlive(pid) {
  if (!pid || !Number.isFinite(pid)) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err && err.code === 'EPERM';
  }
}

export function readLock(lockPath) {
  if (!fs.existsSync(lockPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(lockPath, 'utf8'));
  } catch {
    return null;
  }
}

export function tryAcquireLock(lockPath, meta = {}) {
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  const payload = JSON.stringify({
    pid: process.pid,
    created_at: new Date().toISOString(),
    ...meta,
  });
  try {
    const fd = fs.openSync(lockPath, 'wx');
    try {
      fs.writeFileSync(fd, payload);
    } finally {
      fs.closeSync(fd);
    }
    return { ok: true };
  } catch (err) {
    if (err.code !== 'EEXIST') throw err;
    const existing = readLock(lockPath);
    if (existing && !pidAlive(existing.pid)) {
      try {
        fs.unlinkSync(lockPath);
      } catch {
        // lose the race
      }
      return tryAcquireLock(lockPath, meta);
    }
    const held = new Error(`factory lock held by pid ${existing?.pid ?? 'unknown'}`);
    held.exitCode = EXIT.LOCK;
    held.lock = existing;
    return { ok: false, error: held };
  }
}

export function releaseLock(lockPath) {
  try {
    const existing = readLock(lockPath);
    if (existing && existing.pid !== process.pid) return;
    fs.unlinkSync(lockPath);
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
  }
}

export async function withLock(lockPath, fn, meta = {}) {
  const acquired = tryAcquireLock(lockPath, meta);
  if (!acquired.ok) throw acquired.error;
  try {
    return await fn();
  } finally {
    releaseLock(lockPath);
  }
}
