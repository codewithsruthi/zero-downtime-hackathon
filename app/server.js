import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import { getAppPort, getRoot, loadDotEnv } from '../src/config.js';
import { loadState } from '../src/state.js';
import { withSpan } from '../src/telemetry/otel.js';
import { createStore } from './store.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function renderPage(snap, factoryStatus) {
  const stories = snap.doc?.stories || [];
  const banner = snap.doc
    ? `${stories.length} stories · ${snap.doc.generated_at || ''} · ${snap.source}`
    : 'Waiting for the first successful promote. The factory is up.';
  const rows = stories
    .map((s) => {
      const href = s.url || '#';
      const meta = s.is_job
        ? 'job'
        : `${s.points} points · ${s.comment_count} comments · ${escapeHtml(s.author || '')}`;
      return `<li><a href="${escapeHtml(href)}">${escapeHtml(s.title)}</a><span class="meta">${escapeHtml(meta)}</span></li>`;
    })
    .join('\n');
  const list = rows || '<li class="empty">No stories in the last-known-good document yet.</li>';
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HN digest</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <main>
    <h1>Hacker News digest</h1>
    <p class="banner">Factory ${escapeHtml(factoryStatus)} · ${escapeHtml(banner)}</p>
    <ol>${list}</ol>
  </main>
  <script>
    setTimeout(() => location.reload(), 15000);
  </script>
</body>
</html>`;
}

export function createApp(root = getRoot()) {
  const store = createStore(root);
  const app = express();
  app.disable('x-powered-by');
  app.use(express.static(path.join(HERE, 'public'), { index: false }));

  app.get('/', async (_req, res) => {
    await withSpan('app.request', { 'factory.component': 'app', 'http.route': '/' }, async () => {
      const snap = await withSpan('app.store.load', { 'factory.component': 'app' }, async () => store.load());
      let factoryStatus = 'UNKNOWN';
      try {
        factoryStatus = loadState(root).status;
      } catch {
        factoryStatus = 'UNKNOWN';
      }
      res.status(200).type('html').send(renderPage(snap, factoryStatus));
    });
  });

  app.get('/api/stories', (_req, res) => {
    const snap = store.load();
    res.status(200).json({
      ok: true,
      source: snap.source,
      document: snap.doc,
      stories: snap.doc?.stories || [],
    });
  });

  app.get('/api/health', (_req, res) => {
    const health = store.health();
    let factory_status = 'UNKNOWN';
    try {
      factory_status = loadState(root).status;
    } catch {
      factory_status = 'UNKNOWN';
    }
    res.status(200).json({ ...health, factory_status });
  });

  app.use((_req, res) => {
    res.status(404).type('html').send('<!doctype html><title>Not found</title><p>Not found</p>');
  });

  return app;
}

export function startServer({ root = getRoot(process.env), port = getAppPort(process.env) } = {}) {
  loadDotEnv(root, process.env);
  const app = createApp(root);
  const server = http.createServer(app);
  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      resolve({ app, server, port, root });
    });
  });
}

const launchedDirectly = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (launchedDirectly) {
  const { port } = await startServer();
  console.log(`digest listening on http://127.0.0.1:${port}`);
}
