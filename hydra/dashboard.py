"""Public HYDRA live dashboard. Stdlib only. Does not write data/latest.json."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from hydra.chaos.faults import FAULTS
from hydra.config import load_config, load_dotenv
from hydra.live_snapshot import (
    AMAZON,
    FAULTS_NAME,
    LIVE_NAME,
    empty_snapshot,
    patch_snapshot_fault,
    read_snapshot,
    write_snapshot,
)

# Amazon-tuned args so each named HYDRA fault actually trips this catalog.
FAULT_PRESETS: dict[str, dict[str, Any]] = {
    "http_403": {
        "label": "Loud · HTTP 403 (blocked scrape)",
        "cfg": {},
    },
    "captcha_wall": {
        "label": "Loud · captcha wall",
        "cfg": {},
    },
    "volume_collapse": {
        "label": "Quiet · volume collapse (too few products)",
        "cfg": {"keep": 2},
    },
    "selector_drift": {
        "label": "Quiet · selector drift (0 products extracted)",
        "cfg": {"empty": True},
    },
    "field_rename": {
        "label": "Schema · price field renamed away",
        "cfg": {"from": "price", "to": "amt"},
    },
    "type_change": {
        "label": "Schema · some prices become n/a strings",
        "cfg": {"field": "price", "incompatible": True, "rate": 0.4},
    },
    "null_flood": {
        "label": "Quality · most prices set to null",
        "cfg": {"field": "price", "rate": 0.6},
    },
    "poison_record": {
        "label": "Poison · one bad product row",
        "cfg": {"at": 4},
    },
}


def fault_menu() -> list[dict[str, Any]]:
    out = []
    for fault_id in sorted(FAULTS):
        preset = FAULT_PRESETS.get(fault_id, {})
        out.append(
            {
                "id": fault_id,
                "label": preset.get("label") or fault_id.replace("_", " "),
                "cfg": dict(preset.get("cfg") or {}),
            }
        )
    return out


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HYDRA · Amazon catalog reliability</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:ital,wght@0,400;0,500;0,600;0,700&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&display=swap" rel="stylesheet">
  <script>
    (function(){
      try {
        var t = localStorage.getItem("hydra-theme");
        if (t !== "light" && t !== "dark") t = "dark";
        document.documentElement.setAttribute("data-theme", t);
      } catch (e) {
        document.documentElement.setAttribute("data-theme", "dark");
      }
    })();
  </script>
  <style>
    :root {
      --font-sans: "Avenir Next", "Source Sans 3", "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
      --font-serif: "Iowan Old Style", "Source Serif 4", Palatino, "Palatino Linotype", "Book Antiqua", Georgia, serif;
    }
    :root, html[data-theme="dark"] {
      --bg: #0f1012;
      --ink: #f3efe6;
      --muted: #8d887c;
      --line: #2a2824;
      --panel: #181714;
      --accent: #c4a574;
      --ok: #7dae7a;
      --bad: #c46b63;
      --warn: #c9a14a;
      --scores: #12110f;
      --ribbon-armed: #1c1912;
      --ribbon-broken: #1c1413;
      --ribbon-healed: #141a14;
      --step-current: #1c1912;
      --overlay: rgba(15,16,18,0.82);
      color-scheme: dark;
    }
    html[data-theme="light"] {
      --bg: #f5f1e8;
      --ink: #1b1914;
      --muted: #6b6558;
      --line: #d4ccbb;
      --panel: #fffdf8;
      --accent: #8a5a1a;
      --ok: #2d6b38;
      --bad: #8f433c;
      --warn: #9a6f12;
      --scores: #ece6d6;
      --ribbon-armed: #f6e8c4;
      --ribbon-broken: #f5ddd8;
      --ribbon-healed: #dde8d6;
      --step-current: #f3ead0;
      --overlay: rgba(245,241,232,0.88);
      color-scheme: light;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--font-sans);
      font-size: 15px;
      line-height: 1.45;
    }
    h1, h2, h3, h4, button, select, input, textarea {
      font-family: inherit;
    }
    a { color: inherit; }
    a:visited { color: inherit; }
    header {
      display: flex; align-items: flex-start; justify-content: space-between; gap: 1.5rem;
      padding: 1.35rem 1.75rem 1.1rem; border-bottom: 1px solid var(--line);
    }
    .brand h1 {
      margin: 0;
      font-family: var(--font-serif);
      font-size: 1.55rem; font-weight: 600; letter-spacing: 0.08em;
    }
    .brand p { margin: 0.2rem 0 0; color: var(--muted); font-size: 0.86rem; }
    .brand .byline { margin: 0.4rem 0 0; color: var(--ink); font-size: 0.82rem; }
    .brand .byline a { color: inherit; text-decoration: none; }
    .brand .byline a:hover { color: var(--accent); }
    .header-end { text-align: right; }
    .theme {
      position: fixed; left: 1.15rem; bottom: 0.9rem; z-index: 30;
      display: inline-flex; border: 1px solid var(--line); background: var(--panel);
    }
    .theme button {
      font-family: var(--font-sans);
      font-size: 0.68rem; letter-spacing: 0.08em; text-transform: uppercase;
      background: transparent; color: var(--muted); border: 0; padding: 0.22rem 0.58rem;
      cursor: pointer;
    }
    .theme button + button { border-left: 1px solid var(--line); }
    .theme button[aria-pressed="true"] { background: var(--panel); color: var(--ink); }
    .meta { color: var(--muted); font-size: 0.8rem; text-align: right; line-height: 1.7; }
    .pill {
      display: inline-block; padding: 0.12rem 0.5rem;
      font-size: 0.68rem; letter-spacing: 0.08em; text-transform: uppercase;
      border: 1px solid var(--line); color: var(--muted);
    }
    .pill.healthy { color: var(--ok); border-color: var(--ok); }
    .pill.degraded, .pill.broken, .pill.waiting { color: var(--bad); border-color: var(--bad); }
    .pill.circuit_open { color: var(--warn); border-color: var(--warn); }
    .pill.flash { outline: 1px solid var(--accent); }
    .banner {
      margin: 0; padding: 0.7rem 1.75rem; border-bottom: 1px solid var(--line);
      color: var(--accent); font-size: 0.9rem;
    }
    .banner[hidden] { display: none; }
    .banner.ok { color: var(--ok); }
    .ribbon {
      display: flex; gap: 1rem; align-items: center;
      padding: 0.95rem 1.75rem; border-bottom: 1px solid var(--line);
    }
    .ribbon[hidden] { display: none; }
    .ribbon .kicker {
      font-size: 0.68rem; letter-spacing: 0.12em; font-weight: 700;
      padding: 0.3rem 0.55rem; border: 1px solid; white-space: nowrap;
    }
    .ribbon .headline {
      font-family: var(--font-serif);
      font-size: 1.05rem; font-weight: 600;
    }
    .ribbon .detail { color: var(--muted); font-size: 0.8rem; margin-top: 0.15rem; }
    .ribbon.armed { background: var(--ribbon-armed); }
    .ribbon.armed .kicker { color: var(--warn); border-color: var(--warn); }
    .ribbon.broken { background: var(--ribbon-broken); }
    .ribbon.broken .kicker { color: var(--bad); border-color: var(--bad); }
    .ribbon.healed { background: var(--ribbon-healed); }
    .ribbon.healed .kicker { color: var(--ok); border-color: var(--ok); }
    .controls {
      display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center;
      padding: 0.8rem 1.75rem; border-bottom: 1px solid var(--line);
    }
    .controls[hidden] { display: none; }
    .controls select, .controls button {
      font-family: var(--font-sans); font-size: 15px; line-height: 1.45;
      background: var(--panel); color: var(--ink);
      border: 1px solid var(--line); padding: 0.45rem 0.75rem;
    }
    .controls button { border-color: var(--accent); color: var(--accent); cursor: pointer; }
    .controls button:disabled { opacity: 0.5; cursor: wait; }
    .controls .hint { color: var(--muted); font-size: 0.8rem; max-width: 36rem; }
    .steps {
      display: grid; grid-template-columns: repeat(5, 1fr); gap: 0;
      border-bottom: 1px solid var(--line);
    }
    .step {
      padding: 0.85rem 1rem 0.95rem;
      border-right: 1px solid var(--line);
      min-height: 4.2rem;
    }
    .step:last-child { border-right: 0; }
    .step .idx { display: block; color: var(--muted); font-size: 0.72rem; letter-spacing: 0.1em; font-weight: 700; }
    .step .l { font-family: var(--font-serif); font-size: 1.05rem; margin-top: 0.2rem; }
    .step .n { font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); margin-top: 0.15rem; }
    .step.done { background: var(--ribbon-healed); }
    .step.done .idx, .step.done .l, .step.done .n { color: var(--ok); }
    .step.current { background: var(--ribbon-armed); }
    .step.current .idx, .step.current .l, .step.current .n { color: var(--warn); }
    .step.failed { background: var(--ribbon-broken); }
    .step.failed .idx, .step.failed .l, .step.failed .n { color: var(--bad); }
    main { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(20rem, 0.9fr); min-height: 58vh; }
    section.catalog { padding: 1.2rem 1.75rem 2rem; }
    section.scores {
      padding: 1.2rem 1.5rem 2rem;
      border-left: 1px solid var(--line);
      background: var(--scores);
    }
    h2 {
      font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase;
      color: var(--muted); margin: 0 0 0.9rem; font-weight: 600;
    }
    h3.board-title {
      font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase;
      color: var(--muted); margin: 1rem 0 0.45rem; font-weight: 600;
    }
    h3.board-title:first-of-type { margin-top: 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(15.5rem, 1fr)); gap: 0.7rem; }
    article {
      background: var(--panel); border: 1px solid var(--line); padding: 0.85rem 0.9rem 0.8rem;
      min-height: 7.2rem; display: flex; flex-direction: column; justify-content: space-between;
    }
    article h3 { margin: 0; font-family: var(--font-sans); font-size: 0.92rem; font-weight: 600; line-height: 1.3; }
    article a, article a:link, article a:visited { color: inherit; text-decoration: none; }
    article a:hover { color: var(--accent); }
    article .price {
      margin-top: 0.55rem;
      font-family: var(--font-serif);
      font-size: 1.2rem; color: var(--accent);
    }
    article .meta-row { margin: 0.35rem 0 0; color: var(--muted); font-size: 0.75rem; font-family: var(--font-sans); }
    article.missing { border-color: var(--bad); }
    article.missing .price { color: var(--bad); }
    html[data-theme="light"] article.missing { background: #fff6f4; }
    article.ghost { opacity: 0.4; border-style: dashed; }
    article.dimmed { opacity: 0.4; }
    article.poison { border-color: var(--bad); }
    article.typed .price, article.renamed .price { color: var(--warn); }
    .grid-wrap { position: relative; min-height: 8rem; }
    .grid-overlay {
      position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
      text-align: center; padding: 1rem; background: var(--overlay);
      color: var(--bad); font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
      pointer-events: none;
    }
    .grid-overlay[hidden] { display: none; }
    .empty { color: var(--muted); }
    .board { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
    .metric {
      position: relative; background: var(--panel); border: 1px solid var(--line);
      padding: 0.65rem 0.7rem 0.7rem; cursor: help;
    }
    .metric span {
      color: var(--muted); font-size: 0.65rem; letter-spacing: 0.08em; text-transform: uppercase;
    }
    .metric b {
      display: block; margin-top: 0.25rem;
      font-family: var(--font-serif);
      font-size: 1.15rem; font-weight: 600;
    }
    .metric .sub { color: var(--muted); font-size: 0.72rem; font-weight: 500; font-family: inherit; }
    .metric .tip {
      display: none; position: absolute; z-index: 8; left: 0; bottom: calc(100% + 6px);
      width: 17.5rem; padding: 0.55rem 0.65rem; background: var(--bg);
      border: 1px solid var(--accent); color: var(--ink);
      font-size: 0.78rem; font-style: normal; letter-spacing: 0; text-transform: none;
      line-height: 1.4;
    }
    .metric:hover .tip, .metric:focus-within .tip { display: block; }
    .incident { border: 1px solid var(--line); background: var(--panel); margin: 0 0 0.75rem; }
    .kv { display: grid; grid-template-columns: 7.5rem 1fr; gap: 0.35rem 0.75rem; padding: 0.7rem 0.8rem; }
    .kv + .kv { border-top: 1px solid var(--line); }
    .kv .k { color: var(--muted); font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; }
    .kv .v { font-size: 0.88rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    th, td { text-align: left; padding: 0.4rem 0.35rem; border-bottom: 1px solid var(--line); }
    th { color: var(--muted); font-weight: 500; font-size: 0.68rem; letter-spacing: 0.06em; text-transform: uppercase; }
    .yes { color: var(--ok); }
    .no { color: var(--bad); }
    footer {
      border-top: 1px solid var(--line); padding: 0.75rem 1.75rem 0.75rem 8.25rem; color: var(--muted);
      font-size: 0.75rem; display: flex; align-items: center; justify-content: space-between;
      gap: 1rem; flex-wrap: wrap;
    }
    footer a, footer a:visited { color: var(--accent); }
    @media (max-width: 960px) {
      main, .steps { grid-template-columns: 1fr; }
      .step { border-right: 0; border-bottom: 1px solid var(--line); }
      section.scores { border-left: 0; border-top: 1px solid var(--line); }
      .meta, .header-end { text-align: left; }
      header { flex-direction: column; align-items: flex-start; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>HYDRA</h1>
      <p>Amazon catalog reliability</p>
      <p class="byline">
        <a href="https://www.linkedin.com/in/sruthi-anuvalasetty/" target="_blank" rel="noopener noreferrer">Sruthi Anuvalasetty</a>
        ·
        <a href="https://www.linkedin.com/in/ramachandra-nalam/" target="_blank" rel="noopener noreferrer">Ramachandra Nalam</a>
      </p>
    </div>
    <div class="header-end">
      <div class="meta">
        <div><span id="source">amazon_products</span> · <span id="mode">replay</span></div>
        <div><span id="health" class="pill">waiting</span> · serving <span id="serving">empty</span></div>
      </div>
    </div>
  </header>
  <p id="banner" class="banner">Loading live snapshot…</p>
  <div id="breakRibbon" class="ribbon idle" hidden>
    <div class="kicker" id="ribbonKicker"></div>
    <div>
      <div class="headline" id="ribbonHeadline"></div>
      <div class="detail" id="ribbonDetail"></div>
    </div>
  </div>
  <div class="controls" id="controls" hidden>
    <select id="fault" aria-label="Fault"></select>
    <button type="button" id="breakBtn">Break Amazon</button>
    <button type="button" id="resetBtn">Reset circuit</button>
    <span class="hint" id="action">Inject one fault. Watch the ribbon and catalog, then Detect → Verify. Hover any score for what it means.</span>
  </div>
  <div class="steps" id="steps"></div>
  <main>
    <section class="catalog">
      <h2 id="catalogTitle">Amazon catalog</h2>
      <div class="grid-wrap">
        <div id="catalogOverlay" class="grid-overlay" hidden></div>
        <div id="products" class="grid"><p class="empty">No products yet.</p></div>
      </div>
    </section>
    <section class="scores">
      <h2>Reliability scores</h2>
      <h3 class="board-title">Time to detect &amp; recover</h3>
      <div class="board" id="latency"></div>
      <h3 class="board-title">Heal scoreboard</h3>
      <div class="board" id="healboard"></div>
      <h3 class="board-title">This incident</h3>
      <div id="incident"></div>
    </section>
  </main>
  <footer>
    <div>
      <span id="updated">polling /api/live every 2s</span>
      · <span id="links"></span>
    </div>
  </footer>
  <div class="theme" role="group" aria-label="Color theme">
    <button type="button" id="themeDark" data-theme-set="dark" aria-pressed="true">Dark</button>
    <button type="button" id="themeLight" data-theme-set="light" aria-pressed="false">Light</button>
  </div>
  <script>
    const CONFIG = __CONFIG__;
    const FAULTS = CONFIG.faults || [];
    const STEP_LABELS = {detect:"Detect", classify:"Classify", guard:"Guard", act:"Act", verify:"Verify"};
    let lastHealth = "";
    let playing = false;
    function el(id){ return document.getElementById(id); }
    function esc(s){
      return String(s == null ? "" : s)
        .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
    }
    function secs(v){
      if (v == null || v === "") return "—";
      const n = Number(v);
      if (!Number.isFinite(n)) return "—";
      if (n < 0.01) return "<0.01s";
      if (n < 10) return n.toFixed(2) + "s";
      return n.toFixed(1) + "s";
    }
    function pct(v){
      if (v == null || v === "") return "—";
      const n = Number(v);
      if (!Number.isFinite(n)) return "—";
      return (Math.round(n * 10) / 10) + "%";
    }
    function metric(label, value, tip, sub){
      return `<div class="metric" tabindex="0">
        <span>${esc(label)}</span>
        <b>${esc(value)}${sub ? `<span class="sub"> · ${esc(sub)}</span>` : ""}</b>
        <em class="tip">${esc(tip)}</em>
      </div>`;
    }
    function pill(node, health){
      node.textContent = health;
      node.className = "pill " + health;
      if (lastHealth && lastHealth !== health) {
        node.classList.add("flash");
        setTimeout(() => node.classList.remove("flash"), 900);
      }
      lastHealth = health;
    }
    function render(d){
      el("source").textContent = d.source_id || "amazon_products";
      el("mode").textContent = d.mode || "replay";
      pill(el("health"), d.health || "waiting");
      el("serving").textContent = d.serving || "empty";
      const steps = d.steps || {};
      el("steps").innerHTML = ["detect","classify","guard","act","verify"].map((k,i) =>
        `<div class="step ${esc(steps[k]||"idle")}"><span class="idx">0${i+1}</span><div class="l">${STEP_LABELS[k]}</div><div class="n">${esc(steps[k]||"idle")}</div></div>`
      ).join("");
      const bv = d.break_view || {};
      const ribbon = el("breakRibbon");
      const kicker = {armed:"ARMED", broken:"BROKE"}[bv.state] || "";
      ribbon.hidden = !kicker;
      ribbon.className = "ribbon " + (bv.state || "idle");
      el("ribbonKicker").textContent = kicker;
      el("ribbonHeadline").textContent = bv.headline || "";
      el("ribbonDetail").textContent = bv.detail || "";
      const banner = el("banner");
      banner.hidden = true;
      banner.textContent = "";
      banner.className = "banner";
      const overlays = {
        blocked: "HTTP 403 · scrape blocked",
        captcha: "Captcha wall · not a product feed",
        drift: "Selector drift · 0 products extracted",
      };
      const overlay = el("catalogOverlay");
      const showOverlay = Boolean(overlays[bv.mode] && bv.state === "broken");
      overlay.hidden = !showOverlay;
      overlay.textContent = showOverlay ? overlays[bv.mode] : "";
      const nowRows = d.products_now || [];
      const goodRows = d.products_good || [];
      const products = (bv.cards && bv.cards.length) ? bv.cards : (d.products || []);
      const broken = bv.state === "broken";
      el("catalogTitle").textContent = broken
        ? "This scrape (held back — last-good stays up)"
        : (bv.state === "healed" ? "Amazon catalog · restored" : "Amazon catalog · live");
      el("products").innerHTML = products.length ? products.map(p => {
        const ui = p._ui || {};
        const missing = ui.missing_price || p.price == null || p.price === "";
        let price = "—";
        if (ui.ghost) price = "missing";
        else if (ui.typed) price = typeof p.price === "string" ? p.price : "n/a";
        else if (ui.renamed) price = "renamed";
        else if (!missing && typeof p.price === "number") price = "$"+p.price.toFixed(2);
        else if (!missing) price = String(p.price);
        const showMissing = !ui.ghost && (ui.missing_price || (broken && missing));
        const cls = ["missing","ghost","dimmed","poison","typed","renamed"].filter(k =>
          k === "missing" ? showMissing : ui[k]
        ).join(" ");
        const title = esc(p.title || p.asin || "product");
        const href = p.url && String(p.url).startsWith("http") && !ui.ghost ? p.url : "";
        const head = href ? `<a href="${esc(href)}">${title}</a>` : title;
        const mark = ui.poison ? "POISON" : (ui.ghost ? "dropped" : (p.availability || ""));
        return `<article class="${cls}"><h3>${head}</h3><div class="price">${esc(price)}</div><p class="meta-row">${esc(p.asin||"")}${mark ? " · " + esc(mark) : ""}</p></article>`;
      }).join("") : `<p class="empty">${broken ? "This scrape returned no rows." : "No products in the last-known-good catalog yet."}</p>`;
      const rel = d.reliability || {};
      el("latency").innerHTML = [
        metric("MTTD", secs(rel.mttd_last_s), "Mean time to detect: how long after a failed Amazon scrape HYDRA opened the incident. Big number is the last incident; small number after the dot is the average.", rel.mttd_avg_s == null ? "" : "avg " + secs(rel.mttd_avg_s)),
        metric("MTTA", secs(rel.mtta_last_s), "Mean time to act: how long after detect until the first heal attempt (P1–P8) started.", rel.mtta_avg_s == null ? "" : "avg " + secs(rel.mtta_avg_s)),
        metric("MTTR", secs(rel.mttr_last_s), "Mean time to recover: how long from incident open until it was marked healed, escalated, or blocked.", rel.mttr_avg_s == null ? "" : "avg " + secs(rel.mttr_avg_s)),
        metric("Incidents", rel.incidents == null ? "—" : String(rel.incidents), "How many Amazon incidents HYDRA has opened in this ledger. Healed count is in the subtitle.", rel.incidents_healed == null ? "" : rel.incidents_healed + " healed"),
      ].join("");
      const budget = (rel.budget_used == null || rel.budget_cap == null)
        ? "—"
        : rel.budget_used + " / " + rel.budget_cap;
      el("healboard").innerHTML = [
        metric("Heal success", pct(rel.heal_success_pct), "Share of finished Amazon incidents that ended healed. Backoff (P6) then a later primitive is one incident, not two scores. The table below lists every step of the latest incident.", (rel.incidents_finished == null || rel.incidents_healed == null) ? "" : rel.incidents_healed + " of " + rel.incidents_finished + " incidents"),
        metric("False-heal rate", pct(rel.false_heal_rate_pct), "Share of incidents marked healed where the next scrape still failed within 15 seconds. The fix did not stick.", rel.false_heals == null ? "" : rel.false_heals + " false"),
        metric("Autonomy", pct(rel.autonomy_pct != null ? rel.autonomy_pct : (d.scoreboard || {}).autonomy_pct), "Share of successful heals that needed no human approval (Tier 0–1). Tier 2 schema changes require an approve."),
        metric("Heal budget", budget, "Heal attempts used in the last hour versus the cap of 5. Exhausting the budget opens Guard on purpose."),
      ].join("");
      const run = d.last_run || {};
      const inc = d.incident || {};
      const fault = d.active_fault ? d.active_fault.type : "none";
      const heals = d.heals || [];
      const failed = (d.failed_assertions||[]).join(", ") || "none";
      const healRows = heals.map(h => {
        let status = "open";
        let cls = "";
        if (h.verification_passed) { status = "verified"; cls = "yes"; }
        else if (h.blocked_reason) { status = "blocked"; cls = "no"; }
        else if (h.ended_at && h.primitive === "P6") { status = "backoff"; }
        else if (h.ended_at) { status = "tried"; cls = "no"; }
        return `<tr>
        <td>${esc(h.primitive)}</td><td>${esc(h.attempt)}</td>
        <td class="${cls}">${status}</td>
        <td>${esc(h.notes||h.blocked_reason||"")}</td>
      </tr>`;
      }).join("") || `<tr><td colspan="4" class="empty">No heal attempts yet.</td></tr>`;
      el("incident").innerHTML = `
        <div class="incident">
          <div class="kv"><div class="k">Latest scrape</div><div class="v">${esc(run.status||"—")} · rows ${esc(run.rows_out??"—")} · ${esc(run.error_type||"ok")} · http ${esc(run.http_status??"—")}</div></div>
          <div class="kv"><div class="k">Injected fault</div><div class="v">${esc(fault)}</div></div>
          <div class="kv"><div class="k">Incident class</div><div class="v">${esc(inc.failure_class||"—")} · ${esc(inc.resolution||"none")} · MTTR ${esc(inc.mttr_seconds==null ? "—" : Number(inc.mttr_seconds).toFixed(2))}s</div></div>
          <div class="kv"><div class="k">Quality checks</div><div class="v">${esc(failed)}</div></div>
        </div>
        <table>
          <thead><tr><th>Primitive</th><th>#</th><th>Verify</th><th>Notes</th></tr></thead>
          <tbody>${healRows}</tbody>
        </table>`;
      const links = [];
      if (d.links && d.links.port) links.push(`<a href="${esc(d.links.port)}">Port</a>`);
      if (d.links && d.links.signoz) links.push(`<a href="${esc(d.links.signoz)}">SigNoz</a>`);
      el("links").innerHTML = links.join(" · ") || "Port / SigNoz optional";
      el("updated").textContent = "updated " + (d.updated_at || "") + " · poll 2s";
    }
    async function playFrames(frames){
      playing = true;
      for (const frame of frames) {
        if (!playing) break;
        render(frame);
        await new Promise(resolve => setTimeout(resolve, 1600));
      }
      playing = false;
    }
    async function tick(){
      if (playing) return;
      try {
        const res = await fetch("/api/live", {cache:"no-store"});
        render(await res.json());
      } catch (err) {
        el("banner").hidden = false;
        el("banner").textContent = "Dashboard cannot reach /api/live (" + err + ")";
      }
    }
    async function post(path, body){
      const headers = {"Content-Type":"application/json"};
      if (CONFIG.token) headers["X-Hydra-Token"] = CONFIG.token;
      const res = await fetch(path, {method:"POST", headers, body: JSON.stringify(body)});
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || res.status);
      return data;
    }
    if (CONFIG.controls) {
      el("controls").hidden = false;
      el("fault").innerHTML = FAULTS.map(f =>
        `<option value="${esc(f.id)}">${esc(f.label)}</option>`
      ).join("");
      el("breakBtn").addEventListener("click", async () => {
        const fault = el("fault").value;
        const spec = FAULTS.find(f => f.id === fault) || {};
        const body = Object.assign({fault, once: true}, spec.cfg || {});
        el("breakBtn").disabled = true;
        el("action").textContent = "Fault injected. Watch 01–05 and the catalog cards.";
        try {
          const data = await post("/api/break", body);
          if (data.live) render(data.live);
          if (data.frames && data.frames.length) await playFrames(data.frames);
          else if (data.live) render(data.live);
          el("action").textContent = "Watch the ribbon and the catalog cards.";
        } catch (err) {
          playing = false;
          el("action").textContent = "Break failed: " + err;
        } finally {
          setTimeout(() => { el("breakBtn").disabled = false; }, 2500);
        }
      });
      el("resetBtn").addEventListener("click", async () => {
        el("resetBtn").disabled = true;
        try {
          await post("/api/reset", {});
          el("action").textContent = "Circuit closed. Click Break Amazon again.";
        } catch (err) {
          el("action").textContent = "Reset failed: " + err;
        } finally {
          el("resetBtn").disabled = false;
        }
      });
    }
    function applyTheme(t){
      const next = t === "light" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("hydra-theme", next); } catch (e) {}
      const dark = el("themeDark");
      const light = el("themeLight");
      if (dark && light) {
        dark.setAttribute("aria-pressed", next === "dark" ? "true" : "false");
        light.setAttribute("aria-pressed", next === "light" ? "true" : "false");
      }
    }
    applyTheme(document.documentElement.getAttribute("data-theme") || "dark");
    el("themeDark").addEventListener("click", () => applyTheme("dark"));
    el("themeLight").addEventListener("click", () => applyTheme("light"));
    tick();
    setInterval(tick, 2000);
  </script>
</body>
</html>
"""


@dataclass
class DashboardContext:
    live_path: Path
    faults_path: Path
    source: str
    token: str
    app: Any | None = None
    controls: bool = False
    watch: bool = False
    kick: threading.Event | None = None


def _token_from_env() -> str:
    load_dotenv()
    return (os.environ.get("HYDRA_DASHBOARD_TOKEN") or "").strip()


def _controls_enabled(token: str) -> bool:
    load_dotenv()
    flag = (os.environ.get("HYDRA_DASHBOARD_CONTROLS") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    return bool(token)


def _page(ctx: DashboardContext) -> bytes:
    html = PAGE
    label = (os.environ.get("HYDRA_DASHBOARD_LABEL") or "").strip()
    if label:
        safe = (
            label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        html = html.replace(
            "<p>Amazon catalog reliability</p>",
            f"<p>Amazon catalog reliability · {safe}</p>",
        )
        html = html.replace(
            "<title>HYDRA · Amazon catalog reliability</title>",
            f"<title>HYDRA · {safe}</title>",
        )
    config = json.dumps(
        {
            "controls": ctx.controls,
            "watch": ctx.watch,
            "token": ctx.token if ctx.controls else "",
            "faults": fault_menu(),
        }
    )
    return html.replace("__CONFIG__", config).encode()


def _allow_mutate(handler: BaseHTTPRequestHandler, ctx: DashboardContext) -> bool:
    if ctx.controls and not ctx.token:
        return True
    return _check_token(handler, ctx)


def _bind_from_env() -> tuple[str, int]:
    load_dotenv()
    host = os.environ.get("HYDRA_DASHBOARD_BIND") or "0.0.0.0"
    port = int(os.environ.get("HYDRA_DASHBOARD_PORT") or "8080")
    return host, port


def load_live(ctx: DashboardContext) -> dict[str, Any]:
    snap = read_snapshot(ctx.live_path)
    if snap:
        return snap
    if ctx.app is not None:
        return write_snapshot(ctx.app, source_id=ctx.source)
    return empty_snapshot(ctx.source)


STEP_ORDER = ("detect", "classify", "guard", "act", "verify")


def overlay_steps(
    snap: dict[str, Any],
    *,
    current: str | None = None,
    all_done: bool = False,
    all_failed: bool = False,
) -> dict[str, Any]:
    """Copy a live snapshot and paint the 01–05 heal strip for judges."""
    painted = json.loads(json.dumps(snap, default=str))
    if all_done:
        painted["steps"] = {name: "done" for name in STEP_ORDER}
        painted["phase"] = "idle"
        return painted
    if all_failed:
        painted["steps"] = {name: "failed" for name in STEP_ORDER}
        painted["phase"] = "detect"
        return painted
    steps = {}
    reached = STEP_ORDER.index(current) if current in STEP_ORDER else -1
    for idx, name in enumerate(STEP_ORDER):
        if idx < reached:
            steps[name] = "done"
        elif idx == reached:
            steps[name] = "current"
        else:
            steps[name] = "failed"
    painted["steps"] = steps
    painted["phase"] = current or "detect"
    return painted


def run_break_demo(ctx: DashboardContext, source: str, fault: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Inject, ingest the broken scrape, then heal — return frames the UI can play."""
    _inject_fault(ctx, source, fault, cfg)
    if ctx.app is not None:
        asyncio.run(ctx.app.ingest(source))
    broken = load_live(ctx)
    frames = [
        overlay_steps(broken, all_failed=True),
        overlay_steps(broken, current="detect"),
        overlay_steps(broken, current="classify"),
        overlay_steps(broken, current="guard"),
        overlay_steps(broken, current="act"),
        overlay_steps(broken, current="verify"),
    ]
    resolutions: list[str] = []
    if ctx.app is not None:
        try:
            resolutions = list(_run_heal(ctx, source))
        except RuntimeError:
            resolutions = []
    healed = load_live(ctx)
    frames.append(overlay_steps(healed, all_done=True))
    return {
        "ok": True,
        "injected": fault,
        "source": source,
        "live": frames[0],
        "frames": frames,
        "resolutions": resolutions,
    }


def _check_token(handler: BaseHTTPRequestHandler, ctx: DashboardContext) -> bool:
    if not ctx.token:
        return False
    header = handler.headers.get("X-Hydra-Token") or ""
    auth = handler.headers.get("Authorization") or ""
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    query = parse_qs(urlparse(handler.path).query)
    q = (query.get("token") or [""])[0]
    return ctx.token in {header.strip(), bearer, q}


def make_handler(ctx: DashboardContext):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            if os.environ.get("HYDRA_DASHBOARD_QUIET") == "1":
                return
            super().log_message(fmt, *args)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, indent=2, default=str).encode()
            self._send(code, raw, "application/json; charset=utf-8")

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Hydra-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self._send(200, _page(ctx), "text/html; charset=utf-8")
                return
            if path == "/api/live":
                self._json(200, load_live(ctx))
                return
            self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in {"/api/break", "/api/heal", "/api/reset"}:
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            if not _allow_mutate(self, ctx):
                self._json(
                    403,
                    {
                        "ok": False,
                        "error": "dashboard is read-only; set HYDRA_DASHBOARD_CONTROLS=1 or HYDRA_DASHBOARD_TOKEN",
                    },
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                self._json(400, {"ok": False, "error": "invalid json"})
                return
            if not isinstance(body, dict):
                body = {}
            source = str(body.get("source") or ctx.source)
            if path == "/api/break":
                fault = str(body.get("fault") or "http_403")
                preset = FAULT_PRESETS.get(fault, {})
                cfg = dict(preset.get("cfg") or {})
                cfg.update({k: v for k, v in body.items() if k not in {"source", "fault"}})
                cfg.setdefault("once", True)
                try:
                    payload = run_break_demo(ctx, source, fault, cfg)
                except KeyError as exc:
                    self._json(400, {"ok": False, "error": str(exc)})
                    return
                if ctx.kick is not None:
                    ctx.kick.set()
                self._json(200, payload)
                return
            if path == "/api/reset":
                _reset_circuit(ctx, source)
                if ctx.kick is not None:
                    ctx.kick.set()
                self._json(200, {"ok": True, "reset": source, "live": load_live(ctx)})
                return
            try:
                resolutions = _run_heal(ctx, source)
            except RuntimeError as exc:
                self._json(409, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "resolutions": resolutions, "live": load_live(ctx)})

    return Handler


def _inject_fault(ctx: DashboardContext, source: str, fault: str, cfg: dict[str, Any]) -> None:
    if ctx.app is not None:
        ctx.app.break_source(source, fault, **cfg)
        return
    from hydra.chaos.injector import ChaosInjector

    injector = ChaosInjector(persist_path=ctx.faults_path)
    injector.inject(source, fault, **cfg)
    patch_snapshot_fault(ctx.live_path, source, injector.active(source))


def _reset_circuit(ctx: DashboardContext, source: str) -> None:
    if ctx.app is not None:
        ctx.app.reset_circuit(source)
        return
    from hydra.factory import HydraApp

    app = HydraApp()
    try:
        app.reset_circuit(source)
    finally:
        app.close()


def _run_heal(ctx: DashboardContext, source: str) -> list[str]:
    app = ctx.app
    owned = False
    if app is None:
        from hydra.factory import HydraApp

        app = HydraApp()
        owned = True
    try:
        resolutions = asyncio.run(app.heal_source(source))
        return list(resolutions)
    finally:
        if owned:
            app.close()


async def watch_tick(app, source: str = AMAZON, *, hold_s: float = 0) -> dict[str, Any]:
    """One self-heal beat: ingest, and heal if the run failed."""
    app.injector.load()
    result = await app.ingest(source)
    snap = write_snapshot(app, source_id=source)
    if result.status != "ok":
        if hold_s > 0:
            await asyncio.sleep(hold_s)
        resolutions = await app.heal_source(source)
        try:
            app.store.upsert_source_state(source, current_rung=0)
            app.contracts.patch(source, {"_current_rung": 0})
        except Exception:
            pass
        snap = write_snapshot(app, source_id=source)
        snap["last_resolutions"] = list(resolutions)
        return snap
    try:
        app.store.clear_stale_guard(source)
    except Exception:
        pass
    return write_snapshot(app, source_id=source)


def _watch_loop(
    app,
    source: str,
    interval_s: float,
    stop: threading.Event,
    kick: threading.Event,
    hold_s: float = 0,
) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        while not stop.is_set():
            try:
                loop.run_until_complete(watch_tick(app, source, hold_s=hold_s))
            except Exception as exc:
                print(f"[dashboard watch] {exc}")
            if stop.is_set():
                break
            kick.wait(interval_s)
            kick.clear()
    finally:
        loop.close()


def start_server(
    *,
    host: str | None = None,
    port: int | None = None,
    watch: bool = False,
    source: str = AMAZON,
    app=None,
    live_path: Path | None = None,
    faults_path: Path | None = None,
) -> tuple[ThreadingHTTPServer, threading.Event, Any]:
    load_dotenv()
    default_host, default_port = _bind_from_env()
    host = host if host is not None else default_host
    port = default_port if port is None else port
    owned_app = False
    if watch and app is None:
        from hydra.factory import HydraApp

        app = HydraApp()
        owned_app = True
    cfg = load_config()
    data_dir = app.data_dir if app is not None else cfg.repo_root / "data"
    token = _token_from_env()
    kick = threading.Event()
    ctx = DashboardContext(
        live_path=live_path or (app.live_path if app is not None else data_dir / LIVE_NAME),
        faults_path=faults_path or (app.faults_path if app is not None else data_dir / FAULTS_NAME),
        source=source,
        token=token,
        app=app,
        controls=_controls_enabled(token),
        watch=watch,
        kick=kick if watch else None,
    )
    if app is not None:
        if ctx.controls:
            try:
                app.prepare_demo(source)
            except Exception:
                try:
                    app.reset_circuit(source)
                except Exception:
                    pass
        write_snapshot(app, source_id=source)
    server = ThreadingHTTPServer((host, port), make_handler(ctx))
    stop = threading.Event()
    if watch:
        if app is None:
            raise RuntimeError("watch requires a HydraApp")
        interval = float(
            os.environ.get("HYDRA_DASHBOARD_INTERVAL_S")
            or getattr(app.config, "detect_interval_s", 15)
            or 15
        )
        hold_s = float(os.environ.get("HYDRA_DASHBOARD_HOLD_S") or "3.5")
        worker = threading.Thread(
            target=_watch_loop,
            args=(app, source, interval, stop, kick, hold_s),
            daemon=True,
            name="hydra-dashboard-watch",
        )
        worker.start()
        server._hydra_watch = worker  # type: ignore[attr-defined]
    server._hydra_ctx = ctx  # type: ignore[attr-defined]
    server._hydra_stop = stop  # type: ignore[attr-defined]
    server._hydra_owned_app = app if owned_app else None  # type: ignore[attr-defined]
    return server, stop, app


def serve_forever(
    *,
    watch: bool = False,
    host: str | None = None,
    port: int | None = None,
    source: str = AMAZON,
    app=None,
    live_path: Path | None = None,
    faults_path: Path | None = None,
) -> int:
    server, stop, app = start_server(
        host=host,
        port=port,
        watch=watch,
        source=source,
        app=app,
        live_path=live_path,
        faults_path=faults_path,
    )
    bind_host, bind_port = server.server_address[:2]
    mode = "watch" if watch else "snapshot"
    print(f"HYDRA dashboard ({mode}) http://{bind_host}:{bind_port}")
    if bind_host in {"0.0.0.0", "::"}:
        print(f"publish on this host: http://<server-ip>:{bind_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping dashboard")
    finally:
        stop.set()
        server.shutdown()
        owned = getattr(server, "_hydra_owned_app", None)
        if owned is not None:
            owned.close()
    return 0
