import { URL } from 'node:url';
import { stableId } from '../ids.js';

const JOB_RE = /hiring|\bjobs?\b|who is hiring|ask hn/i;

function unwrapRaw(raw) {
  if (Array.isArray(raw)) return raw;
  if (!raw || typeof raw !== 'object') return [];
  for (const key of ['stories', 'items', 'hits', 'data', 'result', 'records', 'preview_result']) {
    if (Array.isArray(raw[key])) return raw[key];
  }
  return [];
}

function asNumber(value, fallback = 0) {
  if (value == null || value === '') return fallback;
  const n = typeof value === 'number' ? value : Number(String(value).replace(/,/g, ''));
  return Number.isFinite(n) ? n : fallback;
}

function asString(value) {
  if (value == null) return '';
  return String(value).trim();
}

function hostnameOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

function isHnItem(url) {
  return /news\.ycombinator\.com\/item\?id=/.test(url || '');
}

function pickTitle(row) {
  return asString(row.title || row.headline || row.name || row.text);
}

function pickUrl(row) {
  return asString(row.url || row.link || row.href || row.story_url);
}

function pickId(row, title, url) {
  const raw = row.id ?? row.objectID ?? row.story_id;
  if (raw != null && String(raw).length > 0) return String(raw).startsWith('hn-') ? String(raw) : `hn-${raw}`;
  return stableId([url, title]);
}

function detectJob(title, url, row) {
  if (row.is_job === true) return true;
  if (JOB_RE.test(title)) return true;
  if (isHnItem(url) && !row.url && !row.link) return true;
  return false;
}

export function normalizeStory(row, index) {
  const title = pickTitle(row);
  const url = pickUrl(row);
  const points = Math.max(0, asNumber(row.points ?? row.score ?? row.points_count, 0));
  const commentCount = Math.max(0, asNumber(
    row.comment_count ?? row.comments ?? row.descendants ?? row.num_comments,
    0,
  ));
  const author = asString(row.author || row.by || row.user || row.username);
  const age = asString(row.age || row.time_ago || row.created_at) || null;
  const isJob = detectJob(title, url, row);
  const id = pickId(row, title, url);
  const rank = asNumber(row.rank, index + 1);
  return {
    id,
    rank,
    title,
    url,
    site: hostnameOf(url),
    points,
    comment_count: commentCount,
    author,
    age,
    is_job: isJob,
  };
}

export function normalize(raw, { collectorId, runId, source = 'https://news.ycombinator.com', generatedAt } = {}) {
  const rows = unwrapRaw(raw)
    .map((row, i) => normalizeStory(row || {}, i))
    .filter((s) => s.title.length > 0);

  const byUrl = new Map();
  const noUrl = [];
  for (const story of rows) {
    if (!story.url) {
      noUrl.push(story);
      continue;
    }
    const prev = byUrl.get(story.url);
    if (!prev || story.points > prev.points) byUrl.set(story.url, story);
  }
  const deduped = [...byUrl.values(), ...noUrl];
  deduped.sort((a, b) => {
    if (a.rank && b.rank && a.rank !== b.rank) return a.rank - b.rank;
    return b.points - a.points;
  });
  const capped = deduped.slice(0, 30).map((s, i) => ({ ...s, rank: i + 1 }));

  return {
    schema_version: 1,
    generated_at: generatedAt || new Date().toISOString(),
    source,
    collector_id: collectorId || '',
    run_id: runId || '',
    story_count: capped.length,
    stories: capped,
  };
}
