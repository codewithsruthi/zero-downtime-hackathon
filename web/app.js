function el(id) {
  return document.getElementById(id);
}

function esc(value) {
  return String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function money(price) {
  if (typeof price === "number" && Number.isFinite(price)) return `$${price.toFixed(2)}`;
  if (price == null || price === "") return "—";
  return String(price);
}

function seenKey(meta) {
  return [meta.deploymentId || "", meta.commit?.sha || "", meta.builtAt || "", meta.url || ""].join(":");
}

function applyTheme(theme) {
  const next = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("hydra-theme", next);
  } catch {
    /* ignore */
  }
  el("themeDark").setAttribute("aria-pressed", String(next === "dark"));
  el("themeLight").setAttribute("aria-pressed", String(next === "light"));
}

function renderCatalog(products) {
  const root = el("products");
  if (!products.length) {
    root.innerHTML = '<p class="empty">No products in the fixture catalog.</p>';
    return;
  }
  root.innerHTML = products
    .map((p) => {
      const title = esc(p.title || p.asin || "product");
      const href = p.url && String(p.url).startsWith("http") ? p.url : "";
      const head = href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${title}</a>` : title;
      return `<article>
        <h3>${head}</h3>
        <div class="price">${esc(money(p.price))}</div>
        <p class="meta-row">${esc(p.asin || "")}${p.availability ? " · " + esc(p.availability) : ""}</p>
      </article>`;
    })
    .join("");
}

function metric(label, value) {
  return `<div class="metric"><span>${esc(label)}</span><b>${esc(value || "—")}</b></div>`;
}

function showToast(meta) {
  const toast = el("toast");
  const short = meta.commit?.short || (meta.commit?.sha || "").slice(0, 7);
  const env = meta.env || "preview";
  const url = meta.url || location.origin;
  toast.innerHTML = `<strong>Deployed to ${esc(env)}</strong>
    <p>${short ? `<code>${esc(short)}</code> · ` : ""}<a href="${esc(url)}">${esc(url.replace(/^https?:\/\//, ""))}</a></p>`;
  toast.hidden = false;
  window.setTimeout(() => {
    toast.hidden = true;
  }, 8000);
}

function renderDeploy(meta) {
  const env = meta.env || "preview";
  el("deployEnv").textContent = env;
  const sha = meta.commit?.short || (meta.commit?.sha || "").slice(0, 7);
  el("deployBoard").innerHTML = [
    metric("Environment", env),
    metric("Commit", sha || "local"),
    metric("Branch", meta.commit?.ref || "—"),
    metric("Built", meta.builtAt ? new Date(meta.builtAt).toLocaleString() : meta.servedAt || "now"),
  ].join("");
  const bits = [
    meta.source === "runtime" ? "live deploy metadata" : "build metadata",
    sha ? sha : null,
    meta.commit?.message || null,
  ].filter(Boolean);
  el("updated").textContent = bits.join(" · ");

  try {
    const key = `hydra-deploy-toast:${seenKey(meta)}`;
    if ((meta.deploymentId || sha) && !sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, "1");
      showToast(meta);
    }
  } catch {
    showToast(meta);
  }
}

async function loadJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url} ${res.status}`);
  return res.json();
}

async function loadCatalog() {
  try {
    const data = await loadJson("/catalog.json");
    renderCatalog(Array.isArray(data) ? data : []);
  } catch (err) {
    el("products").innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
}

async function loadDeploy() {
  try {
    const live = await loadJson("/api/deploy-meta");
    renderDeploy(live);
    return;
  } catch {
    /* fall through to the file written at build time */
  }
  try {
    renderDeploy(await loadJson("/deploy-meta.json"));
  } catch {
    el("updated").textContent = "Deploy metadata unavailable on this host.";
  }
}

document.querySelectorAll("[data-theme-set]").forEach((btn) => {
  btn.addEventListener("click", () => applyTheme(btn.getAttribute("data-theme-set")));
});
applyTheme(document.documentElement.getAttribute("data-theme") || "dark");
loadCatalog();
loadDeploy();
