const TIMEOUT_MS = 3000;

export async function mcpUpsert({ type, id, props, env = process.env }) {
  const url = env.PORT_MCP_URL;
  if (!url) return { ok: false, skipped: true, error: 'PORT_MCP_URL not set' };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        method: 'tools/call',
        params: { name: 'upsertEntity', arguments: { type, id, props } },
      }),
      signal: ctrl.signal,
    });
    if (!res.ok) return { ok: false, skipped: false, error: `HTTP ${res.status}` };
    return { ok: true, skipped: false };
  } catch (err) {
    return { ok: false, skipped: false, error: err.message };
  } finally {
    clearTimeout(timer);
  }
}
