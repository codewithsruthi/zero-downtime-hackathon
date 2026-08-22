import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

export function atomicWriteFile(dest, contents) {
  const dir = path.dirname(dest);
  fs.mkdirSync(dir, { recursive: true });
  const tmp = path.join(
    dir,
    `.${path.basename(dest)}.${process.pid}.${crypto.randomBytes(4).toString('hex')}.tmp`,
  );
  const fd = fs.openSync(tmp, 'w');
  try {
    fs.writeFileSync(fd, contents);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(tmp, dest);
}

export function atomicWriteJson(dest, obj) {
  atomicWriteFile(dest, `${JSON.stringify(obj, null, 2)}\n`);
}

export function readJsonIfExists(file) {
  if (!fs.existsSync(file)) return null;
  const text = fs.readFileSync(file, 'utf8');
  return JSON.parse(text);
}
