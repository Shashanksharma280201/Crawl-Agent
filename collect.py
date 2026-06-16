#!/usr/bin/env python3
"""Dispatching collector for all non-YouTube platforms.

Usage: python3 collect.py <platform_key>

Hybrid + reliable: agent-browser keeps the headless logged-in browser; cdp drives
navigation/scroll/extract; agent-browser a11y snapshot powers the GENERIC extractor.
Saves atomically to data/<platform>.json. Honest about login + experimental status.
"""
import json
import os
import random
import re
import subprocess
import sys
import time

import browser
import cdp
from platforms import BY_KEY, NEEDS_USERNAME

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ---- generic infinite-scroll until the page stops growing (works anywhere) ----
SCROLL_JS = "(() => { window.scrollTo(0, document.documentElement.scrollHeight); return document.documentElement.scrollHeight; })()"


def log(m):
    print(m, flush=True)


def atomic_write(path, text):
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)


def scroll_until_stall(client, max_rounds=60, stable_target=3):
    last, stable, rnd = -1, 0, 0
    while rnd < max_rounds and stable < stable_target:
        h = client.evaluate(SCROLL_JS)
        time.sleep(random.uniform(2.0, 4.0))
        stable = stable + 1 if h == last else 0
        last = h
        rnd += 1
        if rnd % 3 == 0:
            log(f"    scroll {rnd}: height {h} (stable {stable}/{stable_target})")


# ---------------- Reddit via old.reddit (server-rendered, paginated) ----------------
OLD_REDDIT_JS = r"""
(() => {
  const out = [];
  for (const t of document.querySelectorAll('#siteTable div.thing[data-fullname]')) {
    const fn = t.getAttribute('data-fullname');
    const isC = fn.startsWith('t1_');
    const titleEl = t.querySelector('a.title');
    const body = t.querySelector('div.md');
    out.push({
      type: isC ? 'comment' : 'post',
      title: titleEl ? titleEl.textContent.trim()
                     : (body ? body.textContent.trim().slice(0, 140) : fn),
      subreddit: t.getAttribute('data-subreddit') ? 'r/' + t.getAttribute('data-subreddit') : null,
      author: t.getAttribute('data-author') || null,
      url: t.getAttribute('data-permalink')
           ? 'https://www.reddit.com' + t.getAttribute('data-permalink')
           : (t.getAttribute('data-url') || null),
      meta: t.getAttribute('data-score') ? '⬆ ' + t.getAttribute('data-score') : '',
      body: (isC && body) ? body.textContent.trim() : null,
    });
  }
  return out;
})()
"""


def collect_reddit(client):
    """old.reddit.com/saved auto-redirects to the user's saved page and paginates
    via a 'next' button (no infinite scroll). Follow it page by page."""
    items, url = [], "https://old.reddit.com/saved"
    for page in range(50):
        client.send("Page.navigate", {"url": url})
        time.sleep(3)
        body = (client.evaluate("document.body.innerText.slice(0,300)") or "").lower()
        if "blocked by network security" in body:
            log("[FAIL] reddit blocked the browser (anti-bot)."); break
        raw = client.evaluate(OLD_REDDIT_JS)
        if not raw and "log in" in body and page == 0:
            log("[FAIL] reddit login wall."); break
        items.extend(raw)
        log(f"    page {page + 1}: +{len(raw)} (total {len(items)})")
        nxt = client.evaluate("(()=>{const a=document.querySelector('span.next-button a');return a?a.href:''})()")
        if not nxt:
            break
        url = nxt
        time.sleep(random.uniform(2.0, 4.0))
    return items


USERNAME_JS = {
    # Pinterest: profile link (aria-label) or the unique /username/ link
    "pinterest": "(()=>{let a=document.querySelector(\"a[aria-label*='profile' i]\");if(a)return a.getAttribute('href').replace(/\\//g,'');const ls=[...new Set([...document.querySelectorAll('a[href^=\"/\"]')].map(x=>x.getAttribute('href')).filter(h=>/^\\/[a-zA-Z0-9._-]+\\/$/.test(h)))];return ls.length?ls[0].replace(/\\//g,''):'';})()",
    # TikTok: profile link uses /@handle
    "tiktok": "(()=>{const a=document.querySelector('a[href^=\"/@\"]');return a?a.getAttribute('href').replace('/@','').replace(/\\//g,''):''})()",
    # Instagram: profile link in the nav (best effort)
    "instagram": "(()=>{const a=[...document.querySelectorAll('a[href^=\"/\"]')].find(x=>/^\\/[a-zA-Z0-9._]+\\/$/.test(x.getAttribute('href')||'')&&x.querySelector('img'));return a?a.getAttribute('href').replace(/\\//g,''):''})()",
}


def resolve_username(client, key, tries=5):
    expr = USERNAME_JS.get(key, "(()=>{const a=document.querySelector('a[href^=\"/@\"]');return a?a.getAttribute('href').replace('/@',''):''})()")
    for _ in range(tries):
        try:
            v = (client.evaluate(expr) or "").strip()
            if v:
                return v
        except Exception:
            pass
        time.sleep(2.5)   # SPA header may still be rendering
    return None


# ---------------- Generic a11y extractor (agent-browser) ----------------
A11Y_LINE = re.compile(r'^\s*- link "(?P<t>(?:[^"\\]|\\.)+)" \[[^\]]*url=(?P<u>[^\]\s]+)')


def extract_generic(domain):
    """Parse repeated content links from the a11y snapshot. Best-effort across
    platforms: keep links with substantial text pointing at the platform."""
    snap = subprocess.run(["agent-browser", "snapshot", "-i", "-u"],
                          capture_output=True, text=True, timeout=90).stdout
    items, seen = [], set()
    for line in snap.split("\n"):
        m = A11Y_LINE.match(line)
        if not m:
            continue
        title = m.group("t").replace('\\"', '"').strip()
        url = m.group("u")
        if len(title) < 8 or url in seen or url.endswith("#"):
            continue
        # Keep only real saved-item URLs (drops nav/profile/settings noise).
        if not re.search(r'(/status/|/p/|/posts/|/pin/|/reel/|/video/|/comments/|/feed/update|/watch)', url, re.I):
            continue
        # skip obvious chrome ("Your profile", "Skip to content", etc.)
        if re.match(r'(skip to|your profile|see more|view profile|home|explore|settings)$', title, re.I):
            continue
        seen.add(url)
        items.append({"type": "item", "title": title, "url": url, "author": None, "meta": ""})
    return items


def save(key, items, collection_label):
    for it in items:
        it.setdefault("collection", collection_label)
    atomic_write(os.path.join(DATA, f"{key}.json"),
                 json.dumps(items, ensure_ascii=False, indent=2))
    lines = [f"# {key} saved ({len(items)} items)", ""]
    for i, x in enumerate(items, 1):
        lines.append(f"{i}. {x.get('title')} — {x.get('author') or ''} — {x.get('url')}")
    atomic_write(os.path.join(DATA, f"{key}.md"), "\n".join(lines))


def main(key):
    p = BY_KEY.get(key)
    if not p:
        log(f"[error] unknown platform '{key}'"); return 2

    log(f"[*] {p['name']}: ensuring headless browser…")
    browser.ensure_headless(p["login_url"])
    if not browser.logged_in(p["auth_cookie"], p["domain"]):
        log(f"[FAIL] not logged in to {p['name']}. Open the dashboard and click "
            f"'Log in' on the {p['name']} card.")
        return 3

    host = browser.cdp_host()
    client, _ = cdp.connect(host, url_substr="")
    # Anti-bot: present a normal Chrome UA (not "HeadlessChrome").
    try:
        client.send("Network.setUserAgentOverride", {"userAgent": browser.NORMAL_UA})
    except Exception:
        pass

    # --- Reddit: paginated old.reddit path ---
    if p["extractor"] == "reddit":
        raw = collect_reddit(client)
        client.close()
        seen, items = set(), []
        for it in raw:
            k = it.get("url") or it.get("title")
            if not k or k in seen:
                continue
            seen.add(k)
            it["platform"] = key
            items.append(it)
        save(key, items, "saved")
        log(f"\n[OK] {p['name']}: {len(items)} items -> data/{key}.json")
        return 0

    # --- Everything else: resolve username, navigate, scroll, generic extract ---
    url = p["saved_url"]
    if key in NEEDS_USERNAME:
        client.send("Page.navigate", {"url": "https://www." + p["domain"]})
        time.sleep(4)
        un = resolve_username(client, key)
        if not un:
            log(f"[FAIL] couldn't resolve your {p['name']} username — can't build the saved URL.")
            client.close(); return 4
        url = url.format(username=un)
        log(f"[*] resolved username: {un}")

    log(f"[*] {p['name']}: {url}")
    client.send("Page.navigate", {"url": url})
    time.sleep(6)
    cur = client.evaluate("location.href")
    if re.search(r'(login|signin|sign_in|/i/flow/login|authwall)', cur, re.I):
        log(f"[FAIL] {p['name']} redirected to login ({cur}). Log in via the dashboard.")
        client.close(); return 3

    scroll_until_stall(client)
    raw = extract_generic(p["domain"])
    client.close()

    seen, items = set(), []
    for it in raw:
        k = it.get("url") or it.get("title")
        if not k or k in seen:
            continue
        seen.add(k)
        it["platform"] = key
        items.append(it)

    save(key, items, "saved")
    log(f"\n[OK] {p['name']}: {len(items)} items -> data/{key}.json"
        + ("" if p["status"] == "solid" else "  (experimental — verify the results)"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 collect.py <platform_key>"); sys.exit(2)
    sys.exit(main(sys.argv[1]))
