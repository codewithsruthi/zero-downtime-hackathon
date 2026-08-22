#!/usr/bin/env node
/**
 * Link this GitHub repo to a Vercel project and optionally ship the first deploy.
 * Usage: VERCEL_TOKEN=... node scripts/vercel-connect.mjs [--deploy]
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const PROJECT_NAME = process.env.VERCEL_PROJECT_NAME || "zero-downtime-hackathon";
const REPO = process.env.VERCEL_GIT_REPO || "codewithsruthi/zero-downtime-hackathon";
const TOKEN = (process.env.VERCEL_TOKEN || "").trim();
const wantDeploy = process.argv.includes("--deploy");

if (!TOKEN) {
  process.stderr.write(
    [
      "Missing VERCEL_TOKEN.",
      "Create one at https://vercel.com/account/tokens and rerun:",
      "  VERCEL_TOKEN=... node scripts/vercel-connect.mjs --deploy",
      "",
    ].join("\n")
  );
  process.exit(1);
}

function teamQuery(teamId) {
  return teamId ? `?teamId=${encodeURIComponent(teamId)}` : "";
}

async function api(path, { method = "GET", body, teamId } = {}) {
  const url = `https://api.vercel.com${path}${path.includes("?") ? "" : teamQuery(teamId)}`;
  const res = await fetch(url, {
    method,
    headers: {
      authorization: `Bearer ${TOKEN}`,
      "content-type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const err = new Error(`Vercel ${method} ${path} ${res.status}: ${text}`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

async function main() {
  const user = await api("/v2/user");
  const uid = user.user?.id || user.id;
  const teams = await api("/v2/teams");
  const team = (teams.teams || [])[0];
  const teamId = process.env.VERCEL_ORG_ID || team?.id || "";
  const orgId = teamId || uid;
  process.stdout.write(`Vercel user ${user.user?.username || uid}${team ? ` · team ${team.slug}` : " · hobby"}\n`);

  let project;
  try {
    project = await api(`/v9/projects/${encodeURIComponent(PROJECT_NAME)}`, { teamId });
    process.stdout.write(`Found project ${project.name} (${project.id})\n`);
  } catch (err) {
    if (err.status !== 404) throw err;
    try {
      project = await api("/v11/projects", {
        method: "POST",
        teamId,
        body: {
          name: PROJECT_NAME,
          framework: null,
          buildCommand: "node scripts/vercel-build.mjs",
          outputDirectory: "web",
          installCommand: "true",
          gitRepository: { type: "github", repo: REPO },
        },
      });
      process.stdout.write(`Created project ${project.name} and linked ${REPO}\n`);
    } catch (createErr) {
      if (createErr.status === 400 || createErr.status === 403) {
        process.stdout.write(
          `Git link skipped (${createErr.status}). Creating the project without Git, then you can import ${REPO} in the Vercel dashboard.\n`
        );
        project = await api("/v11/projects", {
          method: "POST",
          teamId,
          body: {
            name: PROJECT_NAME,
            framework: null,
            buildCommand: "node scripts/vercel-build.mjs",
            outputDirectory: "web",
            installCommand: "true",
          },
        });
        process.stdout.write(`Created project ${project.name} (${project.id})\n`);
      } else {
        throw createErr;
      }
    }
  }

  mkdirSync(join(root, ".vercel"), { recursive: true });
  writeFileSync(
    join(root, ".vercel", "project.json"),
    `${JSON.stringify({ orgId, projectId: project.id }, null, 2)}\n`
  );
  process.stdout.write(`Wrote .vercel/project.json\n`);
  process.stdout.write(`VERCEL_ORG_ID=${orgId}\n`);
  process.stdout.write(`VERCEL_PROJECT_ID=${project.id}\n`);
  process.stdout.write(
    [
      "",
      "Add these GitHub Actions secrets:",
      "  VERCEL_TOKEN, VERCEL_ORG_ID, VERCEL_PROJECT_ID",
      "Optional notification secrets:",
      "  NOTIFY_WEBHOOK (Slack or Discord), NTFY_TOPIC",
      "",
    ].join("\n")
  );

  if (!wantDeploy) return;

  const { spawnSync } = await import("node:child_process");
  const deploy = spawnSync(
    "npx",
    ["vercel", "deploy", "--yes", "--prod", `--token=${TOKEN}`],
    { cwd: root, encoding: "utf8", env: { ...process.env, VERCEL_ORG_ID: orgId, VERCEL_PROJECT_ID: project.id } }
  );
  process.stdout.write(deploy.stdout || "");
  process.stderr.write(deploy.stderr || "");
  if (deploy.status !== 0) {
    process.exit(deploy.status || 1);
  }

  const urlMatch = String(deploy.stdout || "").match(/https:\/\/[^\s]+/);
  if (urlMatch) {
    const hookUrl = `${urlMatch[0].replace(/\/$/, "")}/api/vercel-webhook`;
    try {
      await api("/v1/webhooks", {
        method: "POST",
        teamId,
        body: {
          url: hookUrl,
          events: [
            "deployment.created",
            "deployment.succeeded",
            "deployment.error",
            "deployment.canceled",
            "deployment.promoted",
          ],
          projectIds: [project.id],
        },
      });
      process.stdout.write(`Registered Vercel webhook → ${hookUrl}\n`);
    } catch (hookErr) {
      process.stdout.write(`Webhook not registered automatically: ${hookErr.message}\n`);
      process.stdout.write(`Add it in Vercel → Project → Settings → Webhooks → ${hookUrl}\n`);
    }
  }
}

main().catch((err) => {
  process.stderr.write(`${err.message}\n`);
  process.exit(1);
});
