const TIMEOUT_MS = 3000;

export async function restUpsert({ type, id, props, env = process.env }) {
  const base = env.PORT_API_URL;
  const clientId = env.PORT_CLIENT_ID;
  const secret = env.PORT_CLIENT_SECRET;
  if (!base || !clientId || !secret) {
    return { ok: false, skipped: true, error: 'PORT_CLIENT_ID/PORT_CLIENT_SECRET/PORT_API_URL not set' };
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${base.replace(/\/$/, '')}/v1/blueprints/${encodeURIComponent(type)}/entities/${encodeURIComponent(id)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        clientId,
        clientSecret: secret,
      },
      body: JSON.stringify({ identifier: id, properties: props }),
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
