function first(value) {
  if (Array.isArray(value)) return value[0] || "";
  return value || "";
}

export default function handler(req, res) {
  const sha = first(process.env.VERCEL_GIT_COMMIT_SHA);
  const host = first(process.env.VERCEL_URL);
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.status(200).json({
    ok: true,
    source: "runtime",
    env: first(process.env.VERCEL_ENV) || null,
    url: host ? `https://${host}` : null,
    deploymentId: first(process.env.VERCEL_DEPLOYMENT_ID) || null,
    region: first(process.env.VERCEL_REGION) || null,
    commit: {
      sha: sha || null,
      short: sha ? sha.slice(0, 7) : null,
      message: first(process.env.VERCEL_GIT_COMMIT_MESSAGE) || null,
      ref: first(process.env.VERCEL_GIT_COMMIT_REF) || null,
      author: first(process.env.VERCEL_GIT_COMMIT_AUTHOR_LOGIN) || null,
    },
    servedAt: new Date().toISOString(),
  });
}
