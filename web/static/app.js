const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

let HEALTH = { session: {}, platforms: [], busy: null };
let ITEMS = [];
let selected = new Set();
let pollTimer = null, currentJob = null, loginPoll = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pColor = (k) => (HEALTH.platforms.find((p) => p.key === k) || {}).color || "#888";
const pName = (k) => (HEALTH.platforms.find((p) => p.key === k) || {}).name || k;

// ---------- health ----------
async function refresh() {
  try {
    HEALTH = await (await fetch("/api/health")).json();
  } catch { HEALTH = { session: { running: false }, platforms: [] }; }
  renderSidebar();
  renderHealth();
}

function renderHealth() {
  const s = HEALTH.session || {};
  const bh = $("#browser-health");
  bh.className = "health " + (s.running ? (s.logged_in ? "ok" : "down") : "down");
  $("#browser-text").textContent = s.running
    ? (s.logged_in ? "browser ready" : "signed out") : "browser idle";
  $("#account-line").textContent = s.account || "";
}

// ---------- sidebar (platforms + crawl controls) ----------
function renderSidebar() {
  const wrap = $("#side-platforms");
  wrap.innerHTML = HEALTH.platforms.map((p) => {
    const likes = (p.collections || []).filter((c) => c.kind === "likes");
    const likeBoxes = likes.map((c) => `
      <label class="sb-like"><input type="checkbox" class="sb-likecb" data-key="${p.key}" value="${c.key}" />
        <span>${esc(c.name)}</span></label>`).join("");
    const action = !p.logged_in
      ? `<button class="sb-act login" data-key="${p.key}" data-do="login">Log in</button>`
      : `<button class="sb-act crawl" data-key="${p.key}" data-do="crawl" ${p.running ? "disabled" : ""}>${p.running ? "Working…" : "Crawl"}</button>`;
    return `
    <div class="sb-row ${selected.has(p.key) ? "active" : ""}" data-key="${p.key}">
      <button class="sb-main" data-key="${p.key}" title="${esc(p.name)}">
        <span class="sb-ico" style="background:${p.color}"><i class="sb-login-dot ${p.logged_in ? "on" : ""}"></i></span>
        <span class="a-label sb-name">${esc(p.name)}</span>
        <span class="a-label sb-count">${p.count || ""}</span>
      </button>
      <div class="sb-actions">
        ${likeBoxes ? `<div class="sb-likes">${likeBoxes}</div>` : ""}
        ${action}
        <div class="sb-status" id="sb-status-${p.key}"></div>
      </div>
    </div>`;
  }).join("");

  $$("#side-platforms .sb-main").forEach((b) =>
    b.addEventListener("click", () => toggleFilter(b.dataset.key)));
  $$("#side-platforms .sb-act").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      if (b.dataset.do === "crawl") startCrawl(b.dataset.key);
      else platformLogin(b.dataset.key);
    }));

  $("#all-count").textContent = HEALTH.platforms.reduce((a, p) => a + (p.count || 0), 0) || "";
  updateActive();
}

function updateActive() {
  $$("#side-platforms .sb-row").forEach((r) =>
    r.classList.toggle("active", selected.has(r.dataset.key)));
  $("#nav-all").classList.toggle("active", selected.size === 0);
}

// ---------- filtering ----------
function toggleFilter(key) {
  if (selected.has(key)) selected.delete(key); else selected.add(key);
  updateActive();
  renderItems();
  closeNav();
}

// ---------- login ----------
async function platformLogin(key) {
  const st = $(`#sb-status-${key}`);
  if (st) { st.className = "sb-status run"; st.textContent = "Opening login window — sign in there…"; }
  await fetch(`/api/login/${key}`, { method: "POST" });
  if (loginPoll) clearInterval(loginPoll);
  loginPoll = setInterval(async () => {
    await refresh();
    const p = HEALTH.platforms.find((x) => x.key === key);
    if (p && p.logged_in) {
      clearInterval(loginPoll); loginPoll = null;
      const s2 = $(`#sb-status-${key}`);
      if (s2) { s2.className = "sb-status ok"; s2.textContent = "Logged in — ready to crawl"; }
      if (key === "youtube") fetch("/api/account/detect", { method: "POST" }).then(refresh);
    }
  }, 2500);
}

// ---------- crawl ----------
async function startCrawl(key) {
  const p = HEALTH.platforms.find((x) => x.key === key) || { collections: [] };
  // Always crawl the bookmarks/saved collection(s); add Likes only if ticked.
  const base = (p.collections || []).filter((c) => c.kind !== "likes").map((c) => c.key);
  const likes = $$(`.sb-likecb[data-key="${key}"]`).filter((cb) => cb.checked).map((cb) => cb.value);
  const collections = [...base, ...likes];
  const st = $(`#sb-status-${key}`);
  const r = await fetch(`/api/crawl/${key}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ collections }),
  });
  const j = await r.json();
  if (!r.ok) { if (st) { st.className = "sb-status err"; st.textContent = j.message || j.error; } return; }
  if (st) { st.className = "sb-status run"; st.textContent = "Started…"; }
  openDrawer(key); pollStatus(key); refresh();
}

function openDrawer(key) {
  currentJob = key;
  $("#drawer").hidden = false;
  $("#drawer-title").textContent = "Crawling " + pName(key);
  $("#drawer-spinner").style.display = "inline-block";
  $("#drawer-status").textContent = "running"; $("#drawer-log").textContent = "";
}

function pollStatus(key) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const j = await (await fetch(`/api/crawl/${key}/status`)).json();
    if (currentJob === key) { $("#drawer-log").textContent = j.log.join("\n"); $("#drawer-log").scrollTop = 1e9; }
    if (!j.running && j.returncode !== null) {
      clearInterval(pollTimer);
      const ok = j.returncode === 0;
      if (currentJob === key) { $("#drawer-spinner").style.display = "none"; $("#drawer-status").textContent = ok ? "done" : `exit ${j.returncode}`; }
      await refresh(); await loadData();
      const st = $(`#sb-status-${key}`);
      if (st) { st.className = "sb-status " + (ok ? "ok" : "err"); st.textContent = ok ? "Done · refreshed" : `Error (code ${j.returncode})`; }
    }
  }, 1200);
}

// ---------- data / results ----------
async function loadData() {
  ITEMS = (await (await fetch("/api/data")).json()).items;
  renderItems();
}

function renderItems() {
  const q = $("#search").value.trim().toLowerCase();
  let list = ITEMS;
  if (selected.size) list = list.filter((i) => selected.has(i.platform));
  if (q) list = list.filter((i) => [i.title, i.author, i.group].filter(Boolean).join(" ").toLowerCase().includes(q));
  $("#result-count").textContent = list.length;
  $("#empty").hidden = list.length > 0;
  $("#items").innerHTML = list.map((it) => {
    const title = esc(it.title || "(no title)");
    const sub = [it.author, it.group, it.meta].filter(Boolean).map(esc).join(" · ");
    const plat = `<span class="card-plat"><span class="cp-dot" style="background:${pColor(it.platform)}"></span>${esc(pName(it.platform))}</span>`;
    const cls = "card " + (it.image ? "img-card" : "text-card");
    const open = it.url
      ? `<a class="${cls}" href="${esc(it.url)}" target="_blank" rel="noopener">`
      : `<div class="${cls}">`;
    const close = it.url ? "</a>" : "</div>";
    if (it.image) {
      return `${open}
        ${plat}
        <img class="card-img" src="${esc(it.image)}" alt="" loading="lazy"
          onerror="this.closest('.card').classList.add('no-img'); this.remove();" />
        <div class="card-cap">
          <div class="card-title">${title}</div>
          ${sub ? `<div class="card-meta">${sub}</div>` : ""}
        </div>${close}`;
    }
    return `${open}
      <div class="card-head">${plat}<span class="card-tag">${esc(it.type || "item")}</span></div>
      <div class="card-title">${title}</div>
      ${sub ? `<div class="card-meta">${sub}</div>` : ""}${close}`;
  }).join("");
}

// ---------- summary ----------
async function summarize() {
  const panel = $("#summary-panel"), overlay = $("#summary-overlay");
  panel.hidden = false; overlay.hidden = false;
  $("#sp-scope").textContent = selected.size ? `Scope: ${[...selected].map(pName).join(", ")}` : "Scope: all";
  $("#sp-body").innerHTML = `<div class="sp-loading"><span class="spinner"></span> Summarizing…</div>`;
  try {
    const r = await fetch("/api/summary", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platforms: selected.size ? [...selected] : null }) });
    const j = await r.json();
    $("#sp-body").innerHTML = r.ok ? mdToHtml(j.summary) : `<p class="muted">${esc(j.message || j.error)}</p>`;
    if (r.ok) $("#sp-scope").textContent = `${j.count} items · ${j.model}`;
  } catch (e) { $("#sp-body").innerHTML = `<p class="muted">Error</p>`; }
}
function mdToHtml(md) {
  const inline = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
  let html = "", list = false;
  for (const line of String(md || "").split("\n")) {
    const h = line.match(/^(#{1,3})\s+(.*)/), li = line.match(/^\s*[-*]\s+(.*)/);
    if (h) { if (list) { html += "</ul>"; list = false; } html += `<h3>${inline(h[2])}</h3>`; }
    else if (li) { if (!list) { html += "<ul>"; list = true; } html += `<li>${inline(li[1])}</li>`; }
    else if (!line.trim()) { if (list) { html += "</ul>"; list = false; } }
    else { if (list) { html += "</ul>"; list = false; } html += `<p>${inline(line)}</p>`; }
  }
  if (list) html += "</ul>";
  return html;
}

// ---------- mobile nav ----------
function closeNav() { $("#sidebar").classList.remove("open"); $("#nav-scrim").hidden = true; }

// ---------- wire ----------
$("#search").addEventListener("input", renderItems);
$("#summarize").addEventListener("click", summarize);
$("#nav-all").addEventListener("click", () => { selected.clear(); updateActive(); renderItems(); closeNav(); });
$("#nav-toggle").addEventListener("click", () => {
  const open = $("#sidebar").classList.toggle("open");
  $("#nav-scrim").hidden = !open;
});
$("#nav-scrim").addEventListener("click", closeNav);
$("#sp-close").addEventListener("click", () => { $("#summary-panel").hidden = true; $("#summary-overlay").hidden = true; });
$("#summary-overlay").addEventListener("click", () => { $("#summary-panel").hidden = true; $("#summary-overlay").hidden = true; });
$("#drawer-close").addEventListener("click", () => { $("#drawer").hidden = true; });

(async function init() {
  await refresh();
  await loadData();
  setInterval(() => { if (!loginPoll) refresh(); }, 6000);
})();
