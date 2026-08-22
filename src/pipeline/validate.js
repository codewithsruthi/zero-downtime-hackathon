const GATES = ['G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8', 'G9', 'G10', 'G11'];

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isIso8601(value) {
  if (typeof value !== 'string' || value.length < 10) return false;
  const t = Date.parse(value);
  return Number.isFinite(t);
}

function isHttpUrl(value) {
  if (typeof value !== 'string') return false;
  return /^https?:\/\//i.test(value);
}

function result(gates, errors) {
  return { ok: errors.length === 0, gates, errors };
}

export function validate(doc) {
  const gates = Object.fromEntries(GATES.map((g) => [g, true]));
  const errors = [];
  const fail = (gate, message) => {
    gates[gate] = false;
    errors.push({ gate, message });
  };

  if (!isPlainObject(doc)) {
    fail('G1', 'document is not an object');
    for (const g of GATES) if (g !== 'G1') gates[g] = false;
    return result(gates, errors);
  }

  if (doc.schema_version !== 1) fail('G2', `schema_version must be 1, got ${JSON.stringify(doc.schema_version)}`);
  if (!isIso8601(doc.generated_at)) fail('G3', 'generated_at must be ISO-8601');
  if (typeof doc.source !== 'string' || doc.source.trim().length === 0) fail('G4', 'source must be a non-empty string');
  if (!Array.isArray(doc.stories)) {
    fail('G5', 'stories must be an array');
    fail('G6', 'stories.length must be >= 1');
    fail('G7', 'stories missing');
    fail('G8', 'stories missing');
    fail('G9', 'stories missing');
    fail('G10', 'stories missing');
  } else {
    if (doc.stories.length < 1) fail('G6', 'stories.length must be >= 1');
    const urls = [];
    doc.stories.forEach((story, i) => {
      if (!story || typeof story !== 'object') {
        fail('G7', `stories[${i}] is not an object`);
        return;
      }
      if (typeof story.title !== 'string' || story.title.trim().length === 0) {
        fail('G7', `stories[${i}].title is empty`);
      }
      const job = story.is_job === true;
      if (!job && !isHttpUrl(story.url)) {
        fail('G8', `stories[${i}].url must be http(s) unless is_job`);
      }
      const points = story.points;
      const comments = story.comment_count;
      if (!Number.isFinite(points) || points < 0 || !Number.isFinite(comments) || comments < 0) {
        fail('G9', `stories[${i}] points/comment_count must be finite numbers >= 0`);
      }
      if (typeof story.url === 'string' && story.url.length > 0) urls.push(story.url);
    });
    if (new Set(urls).size !== urls.length) fail('G10', 'duplicate story urls');
  }
  if (typeof doc.collector_id !== 'string' || doc.collector_id.trim().length === 0) {
    fail('G11', 'collector_id must be a non-empty string');
  }
  if (typeof doc.run_id !== 'string' || doc.run_id.trim().length === 0) {
    fail('G11', 'run_id must be a non-empty string');
  }

  return result(gates, errors);
}

export function failedGateIds(report) {
  return Object.entries(report.gates)
    .filter(([, ok]) => !ok)
    .map(([id]) => id);
}

export { GATES };
