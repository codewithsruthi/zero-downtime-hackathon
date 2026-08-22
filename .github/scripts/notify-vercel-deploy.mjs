#!/usr/bin/env node
import { readFileSync } from "node:fs";

function readEvent() {
  const path = process.env.GITHUB_EVENT_PATH;
  if (!path) return {};
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return {};
  }
}

function fromDispatch(event) {
  const payload = event.client_payload || {};
  const git = payload.git || {};
  return {
    source: event.action || "vercel.deployment",
    state: payload.state?.type || event.action || "unknown",
    env: payload.environment || "preview",
    url: payload.url || "",
    id: payload.id || "",
    project: payload.project?.name || process.env.GITHUB_REPOSITORY || "hydra",
    sha: git.sha || process.env.GITHUB_SHA || "",
    ref: git.ref || "",
    message: payload.name || "",
  };
}

function fromDeploymentStatus(event) {
  const status = event.deployment_status || {};
  const deployment = event.deployment || {};
  return {
    source: "deployment_status",
    state: status.state || "unknown",
    env: deployment.environment || status.environment || "preview",
    url: status.environment_url || deployment.payload?.web_url || "",
    id: String(deployment.id || ""),
    project: process.env.GITHUB_REPOSITORY || "hydra",
    sha: deployment.sha || process.env.GITHUB_SHA || "",
    ref: deployment.ref || "",
    message: deployment.description || "",
  };
}

function fromEnv() {
  return {
    source: "env",
    state: process.env.DEPLOY_STATE || "success",
    env: process.env.DEPLOY_ENV || "preview",
    url: process.env.DEPLOY_URL || "",
    id: process.env.DEPLOY_ID || "",
    project: process.env.DEPLOY_PROJECT || process.env.GITHUB_REPOSITORY || "hydra",
    sha: process.env.DEPLOY_SHA || process.env.GITHUB_SHA || "",
    ref: process.env.DEPLOY_REF || process.env.GITHUB_REF_NAME || "",
    message: process.env.DEPLOY_MESSAGE || "",
  };
}

function summarize(info) {
  const eventName = process.env.GITHUB_EVENT_NAME || "";
  if (eventName === "repository_dispatch") return fromDispatch(readEvent());
  if (eventName === "deployment_status") return fromDeploymentStatus(readEvent());
  return { ...fromEnv(), ...info };
}

function markdown(info) {
  const short = info.sha ? info.sha.slice(0, 7) : "—";
  const rows = [
    ["Status", info.state || "unknown"],
    ["Environment", info.env || "preview"],
    ["URL", info.url ? `[${info.url}](${info.url})` : "—"],
    ["Commit", `${short}${info.message ? ` — ${info.message}` : ""}`],
    ["Branch", info.ref || "—"],
    ["Deployment", info.id || "—"],
  ];
  return [
    `## HYDRA deployed to Vercel`,
    "",
    ...rows.map(([k, v]) => `- **${k}:** ${v}`),
    "",
    `_Notification from ${info.source}._`,
  ].join("\n");
}

async function githubRequest(path, method, body) {
  const token = process.env.GITHUB_TOKEN;
  const [owner, repo] = (process.env.GITHUB_REPOSITORY || "").split("/");
  if (!token || !owner || !repo) return null;
  const res = await fetch(`https://api.github.com/repos/${owner}/${repo}${path}`, {
    method,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "x-github-api-version": "2022-11-28",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GitHub ${method} ${path} ${res.status}: ${text}`);
  }
  return res.status === 204 ? null : res.json();
}

function slackOrGeneric(info) {
  return {
    text: `${info.project} ${info.state} on ${info.env}${info.url ? ` — ${info.url}` : ""}`,
    event: info,
  };
}

function discordBody(info) {
  return {
    username: "HYDRA / Vercel",
    embeds: [
      {
        title: `${info.project} ${info.state}`,
        url: info.url || undefined,
        color: /error|fail|cancel/i.test(info.state) ? 0xc46b63 : 0x7dae7a,
        description: info.message || info.url || "",
        fields: [
          { name: "Environment", value: info.env || "—", inline: true },
          { name: "Commit", value: info.sha ? info.sha.slice(0, 7) : "—", inline: true },
          { name: "Branch", value: info.ref || "—", inline: true },
        ],
      },
    ],
  };
}

async function forwardWebhook(info) {
  const url = (process.env.NOTIFY_WEBHOOK || "").trim();
  if (!url) return;
  const target = url.toLowerCase();
  const body = target.includes("discord.com/api/webhooks") ? discordBody(info) : slackOrGeneric(info);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`NOTIFY_WEBHOOK ${res.status}`);
}

async function forwardNtfy(info) {
  const topic = (process.env.NTFY_TOPIC || "").trim();
  if (!topic) return;
  const res = await fetch(`https://ntfy.sh/${encodeURIComponent(topic)}`, {
    method: "POST",
    headers: {
      Title: `${info.project} ${info.state}`,
      Tags: /error|fail|cancel/i.test(info.state) ? "x" : "white_check_mark",
      Click: info.url || "",
    },
    body: [info.env, info.url, info.sha, info.message].filter(Boolean).join("\n"),
  });
  if (!res.ok) throw new Error(`ntfy ${res.status}`);
}

async function main() {
  const info = summarize();
  const body = markdown(info);
  if (process.env.GITHUB_STEP_SUMMARY) {
    const { appendFileSync } = await import("node:fs");
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${body}\n`);
  }
  process.stdout.write(`${body}\n`);

  if (info.sha) {
    await githubRequest(`/commits/${info.sha}/comments`, "POST", { body });
  }

  const pr = Number(process.env.DEPLOY_PR || "");
  if (Number.isInteger(pr) && pr > 0) {
    await githubRequest(`/issues/${pr}/comments`, "POST", { body });
  }

  await forwardWebhook(info);
  await forwardNtfy(info);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
