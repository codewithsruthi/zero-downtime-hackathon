#!/usr/bin/env node
import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "web");
mkdirSync(web, { recursive: true });

copyFileSync(join(root, "fixtures", "amazon_products.json"), join(web, "catalog.json"));

const sha = (process.env.VERCEL_GIT_COMMIT_SHA || process.env.GITHUB_SHA || "").trim();
const message = (
  process.env.VERCEL_GIT_COMMIT_MESSAGE ||
  process.env.GITHUB_EVENT_HEAD_COMMIT_MESSAGE ||
  ""
).trim();
const ref = (process.env.VERCEL_GIT_COMMIT_REF || process.env.GITHUB_REF_NAME || "").trim();
const env = (process.env.VERCEL_ENV || "").trim();
const host = (process.env.VERCEL_URL || "").trim();

const meta = {
  ok: true,
  builtAt: new Date().toISOString(),
  env: env || null,
  url: host ? `https://${host}` : null,
  deploymentId: process.env.VERCEL_DEPLOYMENT_ID || null,
  commit: {
    sha: sha || null,
    short: sha ? sha.slice(0, 7) : null,
    message: message || null,
    ref: ref || null,
    author: process.env.VERCEL_GIT_COMMIT_AUTHOR_LOGIN || null,
  },
};

writeFileSync(join(web, "deploy-meta.json"), `${JSON.stringify(meta, null, 2)}\n`);
process.stdout.write("vercel-build: wrote web/catalog.json and web/deploy-meta.json\n");
