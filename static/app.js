const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

let HEALTH = { session: {}, platforms: [], busy: null };
let ITEMS = [];
let selected = new Set();
let pollTimer = null, currentJob = null, loginPoll = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initials = (n) => (n.replace(/[^A-Za-z]/g, "")[0] || "?").toUpperCase();
const pColor = (k) => (HEALTH.platforms.find((p) => p.key === k) || {}).color || "#888";
const pName = (k) => (HEALTH.platforms.find((p) => p.key === k) || {}).name || k;
const loggedIn = () => HEALTH.session && HEALTH.session.logged_in;

// ---------- health / session ----------
async function refresh() {
  try {
    HEALTH = await (await fetch("/api/health")).json();
  } catch { HEALTH = { session: { running: false }, platforms: [] }; }
  renderSession();
  renderSidebar();
  renderKpis();
  renderCrawlCards();
  renderFilters();
}

function renderSession() {
  const s = HEALTH.session || {};
  const banner = $("#session-banner"), text = $("#session-text"),
        sub = $("#session-sub"), btn = $("#login-btn");
  if (!s.running) {
    banner.className = "session-banner down";
    text.textContent = "Browser not started";
    sub.innerHTML = "Click <b>Log in</b> to open a window and sign in.";
    btn.hidden = false; btn.textContent = "Log in";
  } else if (!s.logged_in) {
    banner.className = "session-banner warn";
    text.textContent = "Not logged in";
    sub.innerHTML = "A browser is running but signed out. Click <b>Log in</b>.";
    btn.hidden = false; btn.textContent = "Log in";
  } else {
    banner.className = "session-banner ok";
    text.textContent = "Logged in" + (s.headless ? " · headless" : " · window open");
    sub.innerHTML = s.account
      ? `Account: <span class="mono-account">${esc(s.account)}</span>`
      : "Session ready.";
    btn.hidden = true;
  }
  const bh = $("#browser-health");
  bh.className = "health " + (s.running ? (s.logged_in ? "ok" : "down") : "down");
  $("#browser-text").textContent = s.running
    ? (s.logged_in ? "logged in" : "signed out") : "browser down";
}

function renderSidebar() {
  $("#side-platforms").innerHTML = HEALTH.platforms.map((p) => `
    <div class="side-item" data-key="${p.key}">
      <span class="si-dot" style="background:${p.color}"></span>
      <span class="si-name">${esc(p.name)}</span>
      ${p.count ? `<span class="si-count">${p.count}</span>` : ""}
      ${p.built ? '<span class="si-tag ready">ready</span>' : ""}
    </div>`).join("");
  $$("#side-platforms .side-item").forEach((el) =>
    el.addEventListener("click", () => toggleFilter(el.dataset.key)));
}

function renderKpis() {
  const total = HEALTH.platforms.reduce((a, p) => a + p.count, 0);
  const built = HEALTH.platforms.filter((p) => p.built).length;
  const withData = HEALTH.platforms.filter((p) => p.count > 0).length;
  const k = [
    { label: "Saved items", val: total, sub: `across ${withData} platform(s)` },
    { label: "Collectors ready", val: built, sub: "headless" },
    { label: "Account", val: (HEALTH.session.account || "—").split("@")[0], sub: HEALTH.session.logged_in ? "logged in" : "not logged in" },
    { label: "Platforms", val: HEALTH.platforms.length, sub: "tracked" },
  ];
  $("#kpis").innerHTML = k.map((x) => `
    <div class="kpi"><div class="k-label">${esc(x.label)}</div>
      <div class="k-val" style="font-size:${String(x.val).length>8?'16px':'27px'}">${esc(x.val)}</div>
      <div class="k-sub">${esc(x.sub)}</div></div>`).join("");
}

function renderCrawlCards() {
  const wrap = $("#crawl-grid");
  wrap.innerHTML = "";
  for (const p of HEALTH.platforms) {
    const running = p.running;
    const needLogin = !p.logged_in;
    const tag = p.status === "solid"
      ? '<span class="tag ready">ready</span>'
      : '<span class="tag" style="color:var(--accent);background:#FEF3C7">experimental</span>';
    let label, action, disabled = false, bg = p.color;
    if (running) { label = '<span class="mini-spin"></span> Working…'; action = "none"; disabled = true; }
    else if (needLogin) { label = "Log in"; action = "login"; }
    else if (HEALTH.busy) { label = "Queue busy"; action = "none"; disabled = true; bg = "var(--muted-2)"; }
    else { label = "Crawl"; action = "crawl"; }

    const card = document.createElement("div");
    card.className = "ccard";
    card.innerHTML = `
      <div class="c-top">
        <div class="c-badge" style="background:${p.color}">${initials(p.name)}</div>
        <div><h3>${esc(p.name)}</h3><p class="c-blurb">${esc(p.blurb)}</p></div>
      </div>
      <div class="c-mid"><div class="c-count">${p.count}<small>items</small></div>
        <div style="display:flex;gap:6px;align-items:center">
          <span class="login-dot" title="${p.logged_in ? 'logged in' : 'not logged in'}"
            style="width:8px;height:8px;border-radius:50%;background:${p.logged_in ? 'var(--success)' : 'var(--muted-2)'}"></span>
          ${tag}
        </div></div>
      <button class="btn primary pbtn" data-key="${p.key}" data-action="${action}" ${disabled ? "disabled" : ""}
        style="background:${needLogin ? 'var(--accent)' : bg}">${label}</button>
      <div class="c-status" id="cstatus-${p.key}"></div>`;
    wrap.appendChild(card);
  }
  $$(".btn.pbtn").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.action === "crawl") startCrawl(b.dataset.key);
    else if (b.dataset.action === "login") platformLogin(b.dataset.key);
  }));
}

async function platformLogin(key) {
  const statusEl = $(`#cstatus-${key}`);
  statusEl.className = "c-status run";
  statusEl.textContent = "Opening login window — sign in there…";
  await fetch(`/api/login/${key}`, { method: "POST" });
  if (loginPoll) clearInterval(loginPoll);
  loginPoll = setInterval(async () => {
    await refresh();
    const p = HEALTH.platforms.find((x) => x.key === key);
    if (p && p.logged_in) {
      clearInterval(loginPoll); loginPoll = null;
      statusEl.className = "c-status ok"; statusEl.textContent = "Logged in — ready to crawl";
      if (key === "youtube") fetch("/api/account/detect", { method: "POST" }).then(refresh);
    }
  }, 2500);
}

// ---------- filters / data ----------
function toggleFilter(key) {
  if (selected.has(key)) selected.delete(key); else selected.add(key);
  renderFilters(); renderItems();
}
function renderFilters() {
  const withData = HEALTH.platforms.filter((p) => p.count > 0);
  $("#filter-chips").innerHTML = withData.map((p) => `
    <button class="chip ${selected.has(p.key) ? "active" : ""}" data-key="${p.key}">
      <span class="chip-dot" style="background:${p.color}"></span>${esc(p.name)}
      <span class="chip-count">${p.count}</span></button>`).join("");
  $$("#filter-chips .chip").forEach((c) => c.addEventListener("click", () => toggleFilter(c.dataset.key)));
  $("#clear-filters").hidden = selected.size === 0;
}
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
  $("#items").innerHTML = list.map((it) => `
    <div class="item">
      <div class="i-head">
        <span class="i-pdot" style="background:${pColor(it.platform)}"></span>
        <span class="i-plat">${esc(pName(it.platform))}</span>
        <span class="i-type">${esc(it.type || "item")}</span>
      </div>
      ${it.url ? `<a class="i-title" href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title || "(no title)")}</a>`
               : `<span class="i-title">${esc(it.title || "(no title)")}</span>`}
      <div class="i-sub">${it.group ? `<span class="grp">${esc(it.group)}</span>` : ""}${it.author ? " · " + esc(it.author) : ""}</div>
      ${it.meta ? `<div class="i-meta">${esc(it.meta)}</div>` : ""}
    </div>`).join("");
}

// ---------- login ----------
async function doLogin() {
  $("#login-btn").disabled = true;
  $("#session-sub").innerHTML = "Opening a window… <b>sign in there</b>, this updates automatically.";
  await fetch("/api/login/youtube", { method: "POST" });
  if (loginPoll) clearInterval(loginPoll);
  loginPoll = setInterval(async () => {
    await refresh();
    if (loggedIn()) {
      clearInterval(loginPoll);
      $("#login-btn").disabled = false;
      fetch("/api/account/detect", { method: "POST" }).then(refresh);
    }
  }, 2500);
}

// ---------- crawl ----------
async function startCrawl(key) {
  const statusEl = $(`#cstatus-${key}`);
  const r = await fetch(`/api/crawl/${key}`, { method: "POST" });
  const j = await r.json();
  if (!r.ok) { statusEl.className = "c-status err"; statusEl.textContent = j.message || j.error; return; }
  statusEl.className = "c-status run"; statusEl.textContent = "Started…";
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
      const st = $(`#cstatus-${key}`); st.className = "c-status " + (ok ? "ok" : "err");
      st.textContent = ok ? "Completed · refreshed" : `Finished (code ${j.returncode})`;
      await refresh(); await loadData();
    }
  }, 1200);
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

// ---------- wire ----------
$("#search").addEventListener("input", renderItems);
$("#clear-filters").addEventListener("click", () => { selected.clear(); renderFilters(); renderItems(); });
$("#login-btn").addEventListener("click", doLogin);
$("#summarize").addEventListener("click", summarize);
$("#sp-close").addEventListener("click", () => { $("#summary-panel").hidden = true; $("#summary-overlay").hidden = true; });
$("#summary-overlay").addEventListener("click", () => { $("#summary-panel").hidden = true; $("#summary-overlay").hidden = true; });
$("#drawer-close").addEventListener("click", () => { $("#drawer").hidden = true; });

(async function init() {
  await refresh();
  await loadData();
  setInterval(() => { if (!loginPoll) refresh(); }, 6000);
})();
