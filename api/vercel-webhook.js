function asRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function deploymentFrom(body) {
  const payload = asRecord(body.payload);
  const deployment = asRecord(payload.deployment);
  const git = asRecord(payload.git);
  const project = asRecord(payload.project);
  const url = String(deployment.url || payload.url || "").replace(/^https?:\/\//, "");
  return {
    type: String(body.type || payload.type || "deployment"),
    state: String(deployment.readyState || payload.state || body.type || "unknown"),
    env: String(payload.target || deployment.target || payload.environment || "preview"),
    url: url ? `https://${url}` : "",
    id: String(deployment.id || payload.id || ""),
    project: String(project.name || deployment.name || "hydra"),
    sha: String(git.sha || asRecord(deployment.meta).githubCommitSha || ""),
    ref: String(git.ref || asRecord(deployment.meta).githubCommitRef || ""),
    message: String(asRecord(deployment.meta).githubCommitMessage || ""),
  };
}

function slackBody(event) {
  return {
    text: `${event.project} ${event.state} on ${event.env}`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: [
            `*${event.project}* \`${event.state}\` · ${event.env}`,
            event.url ? `<${event.url}|Open deployment>` : "",
            event.sha ? `Commit \`${event.sha.slice(0, 7)}\` ${event.ref}`.trim() : "",
            event.message ? event.message : "",
          ]
            .filter(Boolean)
            .join("\n"),
        },
      },
    ],
  };
}

function discordBody(event) {
  const color = /error|fail|cancel/i.test(event.state) ? 0xc46b63 : 0x7dae7a;
  return {
    username: "HYDRA / Vercel",
    embeds: [
      {
        title: `${event.project} ${event.state}`,
        url: event.url || undefined,
        color,
        fields: [
          { name: "Environment", value: event.env || "—", inline: true },
          { name: "Commit", value: event.sha ? event.sha.slice(0, 7) : "—", inline: true },
          { name: "Branch", value: event.ref || "—", inline: true },
        ],
        description: event.message || event.url || "",
      },
    ],
  };
}

async function forward(url, event) {
  const target = url.toLowerCase();
  let body;
  if (target.includes("discord.com/api/webhooks")) body = discordBody(event);
  else if (target.includes("hooks.slack.com") || target.includes("slack.com")) body = slackBody(event);
  else body = { text: `${event.project} ${event.state} ${event.env} ${event.url}`.trim(), event };

  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`notify webhook ${res.status}`);
  }
}

async function ntfy(topic, event) {
  const res = await fetch(`https://ntfy.sh/${encodeURIComponent(topic)}`, {
    method: "POST",
    headers: {
      Title: `${event.project} ${event.state}`,
      Tags: /error|fail|cancel/i.test(event.state) ? "x" : "white_check_mark",
      Click: event.url || "",
      Priority: event.env === "production" ? "high" : "default",
    },
    body: [event.env, event.url, event.sha, event.message].filter(Boolean).join("\n"),
  });
  if (!res.ok) {
    throw new Error(`ntfy ${res.status}`);
  }
}

export default async function handler(req, res) {
  if (req.method === "GET") {
    res.status(200).json({ ok: true, listener: "vercel-webhook" });
    return;
  }
  if (req.method !== "POST") {
    res.status(405).json({ ok: false, error: "method not allowed" });
    return;
  }

  const event = deploymentFrom(req.body || {});
  const results = [];
  const webhook = (process.env.NOTIFY_WEBHOOK || "").trim();
  const topic = (process.env.NTFY_TOPIC || "").trim();

  try {
    if (webhook) {
      await forward(webhook, event);
      results.push("webhook");
    }
    if (topic) {
      await ntfy(topic, event);
      results.push("ntfy");
    }
    res.status(200).json({ ok: true, forwarded: results, event });
  } catch (err) {
    res.status(502).json({ ok: false, error: err instanceof Error ? err.message : String(err), event });
  }
}
