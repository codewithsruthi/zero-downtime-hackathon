import fs from 'node:fs';
import { EXIT, paths } from '../config.js';
import { validate } from '../pipeline/validate.js';

export async function validateCommand(ctx) {
  const file = ctx.flags.input || paths(ctx.root).candidate;
  if (!fs.existsSync(file)) {
    return { exitCode: EXIT.FILE, result: { error: `missing ${file}` } };
  }
  let doc;
  try {
    doc = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (err) {
    return { exitCode: EXIT.PARSE, result: { error: err.message } };
  }
  const report = validate(doc);
  return { exitCode: report.ok ? EXIT.SUCCESS : EXIT.VALIDATION, result: { file, report } };
}
