import fs from 'node:fs';
import { EXIT, paths } from '../config.js';
import { loadState } from '../state.js';

export async function statusCommand(ctx) {
  const { root } = ctx;
  const p = paths(root);
  const state = loadState(root);
  const result = {
    state,
    latest_exists: fs.existsSync(p.latest),
    candidate_exists: fs.existsSync(p.candidate),
    broken: fs.existsSync(p.brokenMarker),
    healed: fs.existsSync(p.healedMarker),
  };
  return { exitCode: EXIT.SUCCESS, result };
}
