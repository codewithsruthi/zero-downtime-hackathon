import fs from 'node:fs';
import { paths } from '../src/config.js';
import { validate } from '../src/pipeline/validate.js';

export function createStore(root) {
  let cache = { doc: null, mtimeMs: null, lastGood: null, source: 'empty' };

  function readLatest() {
    const file = paths(root).latest;
    if (!fs.existsSync(file)) {
      return { doc: cache.lastGood, source: cache.lastGood ? 'last-known-good' : 'absent', error: null };
    }
    const st = fs.statSync(file);
    if (cache.doc && cache.mtimeMs === st.mtimeMs) {
      return { doc: cache.doc, source: 'cache', error: null };
    }
    try {
      const doc = JSON.parse(fs.readFileSync(file, 'utf8'));
      const report = validate(doc);
      if (!report.ok) {
        return {
          doc: cache.lastGood,
          source: cache.lastGood ? 'last-known-good' : 'corrupt',
          error: 'latest.json failed validation',
        };
      }
      cache = { doc, mtimeMs: st.mtimeMs, lastGood: doc, source: 'disk' };
      return { doc, source: 'disk', error: null };
    } catch (err) {
      return {
        doc: cache.lastGood,
        source: cache.lastGood ? 'last-known-good' : 'corrupt',
        error: err.message,
      };
    }
  }

  return {
    load() {
      return readLatest();
    },
    health() {
      const snap = readLatest();
      const stories = snap.doc?.stories || [];
      let status = 'ok';
      if (snap.source === 'corrupt' || snap.source === 'last-known-good') status = 'degraded';
      else if (!snap.doc) status = 'waiting';
      return {
        status,
        story_count: stories.length,
        generated_at: snap.doc?.generated_at || null,
        source: snap.source,
        error: snap.error,
      };
    },
  };
}
