#!/usr/bin/env python3
"""Headless YouTube collector (Watch Later + Liked) — HYBRID.

agent-browser keeps the headless, logged-in Chrome alive; cdp.py does the fast,
crash-resistant extraction (one Runtime.evaluate per page). Saves incrementally
and atomically so a crash never loses or corrupts data.
"""
import json
import os
import random
import re
import sys
import time

import browser
import cdp

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT_JSON = os.path.join(DATA, "youtube.json")
OUT_MD = os.path.join(DATA, "youtube.md")

COLLECTIONS = [
    {"key": "watch_later", "name": "Watch Later", "url": "https://www.youtube.com/playlist?list=WL"},
    {"key": "liked",       "name": "Liked videos", "url": "https://www.youtube.com/playlist?list=LL"},
]
COUNT_JS = "(() => document.querySelectorAll('ytd-playlist-video-renderer, yt-lockup-view-model').length)()"
SCROLL_JS = "(() => { window.scrollTo(0, document.documentElement.scrollHeight); return 1; })()"

# Core-field extractor for BOTH layouts (old renderer + new lockup).
EXTRACT_JS = r"""
(() => {
  const out = [];
  const vid = (h) => { const m = (h||'').match(/[?&]v=([^&]+)/); return m ? m[1] : null; };

  for (const r of document.querySelectorAll('ytd-playlist-video-renderer')) {
    const a = r.querySelector('a#video-title');
    const ch = r.querySelector('ytd-channel-name a');
    const dur = r.querySelector('ytd-thumbnail-overlay-time-status-renderer #text, #text.ytd-thumbnail-overlay-time-status-renderer, .badge-shape-wiz__text');
    const href = a ? a.getAttribute('href') : null;
    out.push({
      title: a ? (a.getAttribute('title') || a.textContent.trim()) : null,
      channel: ch ? ch.textContent.trim() : null,
      duration: dur ? dur.textContent.trim() : null,
      video_id: vid(href), href,
    });
  }

  for (const r of document.querySelectorAll('yt-lockup-view-model')) {
    const a = r.querySelector('a[href*="/watch"]:not(.ytLockupViewModelContentImage)')
           || [...r.querySelectorAll('a[href*="/watch"]')].find(x => x.textContent.trim().length > 6);
    const ch = r.querySelector('a[href^="/@"], a[href*="/channel/"], a[href*="/user/"]');
    let dur = null;
    for (const b of r.querySelectorAll('badge-shape, .badge-shape-wiz__text')) {
      const t = b.textContent.trim();
      if (/^\d{1,2}(:\d{2})+$/.test(t)) { dur = t; break; }
    }
    const href = a ? a.getAttribute('href') : null;
    out.push({
      title: a ? (a.getAttribute('title') || a.textContent.trim()) : null,
      channel: ch ? ch.textContent.trim() : null,
      duration: dur,
      video_id: vid(href), href,
    });
  }
  return out;
})()
"""


def log(m):
    print(m, flush=True)


def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def save(items):
    atomic_write(OUT_JSON, json.dumps(items, ensure_ascii=False, indent=2))
    labels = {"watch_later": "Watch Later", "liked": "Liked videos"}
    lines = [f"# YouTube saved ({len(items)} items)", ""]
    by = {}
    for it in items:
        by.setdefault(it["collection"], []).append(it)
    for k, g in by.items():
        lines.append(f"## {labels.get(k, k)} ({len(g)})\n")
        for i, x in enumerate(g, 1):
            lines.append(f"{i}. {x['title']} — {x.get('channel') or '(no channel)'} — {x['url']}")
        lines.append("")
    atomic_write(OUT_MD, "\n".join(lines))


def collect_one(client, coll, acc):
    log(f"[*] {coll['name']}: {coll['url']}")
    client.send("Page.navigate", {"url": coll["url"]})
    time.sleep(6)

    last, stable, rnd = -1, 0, 0
    while rnd < 80 and stable < 3:
        client.evaluate(SCROLL_JS)
        time.sleep(random.uniform(2.0, 4.0))
        cnt = client.evaluate(COUNT_JS)
        stable = stable + 1 if cnt == last else 0
        last = cnt
        rnd += 1
        log(f"    scroll {rnd}: {cnt} loaded (stable {stable}/3)")

    raw = client.evaluate(EXTRACT_JS)
    added = 0
    for v in raw:
        vid = v.get("video_id")
        key = vid or v.get("href")
        if not key or key in acc:
            continue
        acc[key] = {
            "type": "video", "collection": coll["key"],
            "title": v.get("title"), "channel": v.get("channel"),
            "duration": v.get("duration"),
            "url": f"https://www.youtube.com/watch?v={vid}" if vid else (
                ("https://www.youtube.com" + v["href"]) if v.get("href", "").startswith("/") else None),
            "video_id": vid,
        }
        added += 1
    log(f"[=] {coll['name']}: +{added} (total {len(acc)})")
    return added


def main():
    log("[*] ensuring headless, logged-in browser…")
    browser.ensure_headless("https://www.youtube.com")
    if not browser.logged_in():
        log("[FAIL] not logged in — open the dashboard and click 'Log in'.")
        return 2

    host = browser.cdp_host()
    client, _ = cdp.connect(host, url_substr="")
    acc = {}
    try:
        for coll in COLLECTIONS:
            collect_one(client, coll, acc)
            save(list(acc.values()))     # incremental + atomic after each collection
    finally:
        client.close()

    items = list(acc.values())
    wl = sum(1 for x in items if x["collection"] == "watch_later")
    ll = sum(1 for x in items if x["collection"] == "liked")
    miss = sum(1 for x in items if not x["url"] or not x["title"])
    log(f"\n[OK] {len(items)} items (Watch Later {wl}, Liked {ll}) | empty url/title: {miss}")
    log(f"[OK] saved -> {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
