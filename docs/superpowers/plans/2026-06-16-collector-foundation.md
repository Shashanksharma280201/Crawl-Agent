# Collector Foundation Implementation Plan (Plan A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken generic extractor architecture with a plugin-registry + generic-engine design, proven end-to-end with YouTube + Reddit, plus the new web UI Likes toggle and the macOS port fix.

**Architecture:** Each platform is a small module declaring metadata + a list of collections (each with a URL, a DOM-extraction JS snippet, and a nav strategy). A single generic engine runs the crawl loop for any platform: ensure headless → login check → for each requested collection: navigate → scroll/paginate → CDP `Runtime.evaluate(extract_js)` → normalize → dedup → atomic incremental save. The Flask app calls the engine in-process (no subprocess) and exposes per-platform collections so the UI can render Likes opt-in checkboxes.

**Tech Stack:** Python 3.8+, Flask, websocket-client (CDP), agent-browser (headless Chrome), pytest (new, for unit tests).

**Scope note:** This plan ports only YouTube + Reddit onto the new engine (the two known-good platforms). The remaining six platform extractors (Twitter, Pinterest, LinkedIn, Instagram, TikTok, Facebook) are **Plan B**, written after this foundation is verified working.

**Data shapes (canonical, used across all tasks):**

- Every platform `extract_js` returns a JS array of raw item objects of shape:
  `{ type, title, author, url, meta }` (extra fields like `body`, `subreddit` may be present and pass through). `url` is absolute. Items with no `url` are dropped by the engine.
- The engine adds `platform` and `collection` to each item before saving.
- Dedup key for an item: `(item["collection"], item["url"] or item["title"])`.

---

### Task 1: Test tooling + package skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `conftest.py`
- Create: `collector/__init__.py` (empty)
- Create: `collector/platforms/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Add pytest to requirements**

Append to `requirements.txt`:

```
pytest
```

- [ ] **Step 2: Create the empty package/test marker files**

```bash
mkdir -p collector/platforms tests
touch collector/__init__.py collector/platforms/__init__.py tests/__init__.py
```

- [ ] **Step 3: Create `conftest.py` at repo root**

```python
# Ensures the repo root is importable so `import collector` works under pytest.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

- [ ] **Step 4: Install and verify pytest runs**

Run: `python3 -m pip install -q pytest && python3 -m pytest -q`
Expected: pytest runs and reports "no tests ran" (exit code 5) — no import errors.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt conftest.py collector tests
git commit -m "chore: add pytest tooling and package skeleton"
```

---

### Task 2: Platform contract (`base.py`)

**Files:**
- Create: `collector/platforms/base.py`
- Test: `tests/test_base.py`

- [ ] **Step 1: Write the failing test**

`tests/test_base.py`:

```python
import pytest

from collector.platforms.base import Collection, Platform, validate_platform


def _collection(key="saved", kind="bookmarks", nav="scroll", next_js=""):
    return Collection(key=key, name=key.title(), kind=kind, url="https://e.com/s",
                      nav=nav, extract_js="[]", next_js=next_js)


def _platform(collections):
    return Platform(key="e", name="E", color="#000", blurb="b", domain="e.com",
                    auth_cookie="c", login_url="https://e.com/login",
                    collections=tuple(collections))


def test_default_collection_is_first():
    p = _platform([_collection("a"), _collection("b")])
    assert p.default_collection.key == "a"


def test_validate_rejects_duplicate_collection_keys():
    p = _platform([_collection("x"), _collection("x")])
    with pytest.raises(ValueError):
        validate_platform(p)


def test_validate_rejects_empty_collections():
    p = _platform([])
    with pytest.raises(ValueError):
        validate_platform(p)


def test_validate_requires_next_js_for_paginate():
    p = _platform([_collection(nav="paginate", next_js="")])
    with pytest.raises(ValueError):
        validate_platform(p)


def test_validate_accepts_valid_platform():
    p = _platform([_collection(), _collection("liked", kind="likes")])
    validate_platform(p)  # should not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_base.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'collector.platforms.base'`.

- [ ] **Step 3: Write `collector/platforms/base.py`**

```python
"""Platform/Collection contract shared by every platform module + the engine."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Collection:
    key: str                 # unique within a platform, e.g. "bookmarks", "likes"
    name: str                # UI/MD label, e.g. "Bookmarks"
    kind: str                # "bookmarks" | "likes"
    url: str                 # may contain "{username}"
    nav: str                 # "scroll" | "paginate"
    extract_js: str          # JS returning an array of {type,title,author,url,meta}
    next_js: str = ""        # paginate only: JS returning next page URL or ""
    count_js: str = ""       # scroll only: JS probe for stall detection (optional)


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    color: str
    blurb: str
    domain: str
    auth_cookie: str
    login_url: str
    collections: tuple
    needs_username: bool = False
    username_js: str = ""

    @property
    def default_collection(self):
        return self.collections[0]


def validate_platform(p):
    """Raise ValueError if the platform contract is malformed."""
    if not p.key:
        raise ValueError("platform key is empty")
    if not p.collections:
        raise ValueError(f"{p.key}: no collections declared")
    keys = [c.key for c in p.collections]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{p.key}: duplicate collection keys {keys}")
    for c in p.collections:
        if c.kind not in ("bookmarks", "likes"):
            raise ValueError(f"{p.key}.{c.key}: bad kind {c.kind!r}")
        if c.nav not in ("scroll", "paginate"):
            raise ValueError(f"{p.key}.{c.key}: bad nav {c.nav!r}")
        if c.nav == "paginate" and not c.next_js:
            raise ValueError(f"{p.key}.{c.key}: paginate needs next_js")
        if p.needs_username and "{username}" in c.url and not p.username_js:
            raise ValueError(f"{p.key}: needs_username but no username_js")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_base.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add collector/platforms/base.py tests/test_base.py
git commit -m "feat: platform/collection contract with validation"
```

---

### Task 3: YouTube + Reddit platform modules

**Files:**
- Create: `collector/platforms/youtube.py`
- Create: `collector/platforms/reddit.py`
- Test: `tests/test_platform_modules.py`

- [ ] **Step 1: Write the failing test**

`tests/test_platform_modules.py`:

```python
from collector.platforms import youtube, reddit
from collector.platforms.base import validate_platform


def test_youtube_has_two_collections_with_likes():
    p = youtube.PLATFORM
    validate_platform(p)
    keys = [c.key for c in p.collections]
    assert keys == ["watch_later", "liked"]
    assert p.collections[1].kind == "likes"


def test_reddit_saved_paginates():
    p = reddit.PLATFORM
    validate_platform(p)
    assert p.collections[0].key == "saved"
    assert p.collections[0].nav == "paginate"
    assert p.collections[0].next_js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_platform_modules.py -q`
Expected: FAIL with `ImportError`/`ModuleNotFoundError` for `youtube`.

- [ ] **Step 3: Write `collector/platforms/youtube.py`**

```python
"""YouTube: Watch Later (bookmarks) + Liked videos (likes)."""
from collector.platforms.base import Collection, Platform

# Stall probe: number of rendered video rows (both layouts). More reliable than
# scrollHeight for YouTube's virtualized playlist pages.
_COUNT_JS = ("(() => document.querySelectorAll("
             "'ytd-playlist-video-renderer, yt-lockup-view-model').length)()")

# Returns canonical items: {type,title,author,url,meta}. Handles both the old
# renderer layout and the new lockup layout. Builds absolute watch URLs inline.
_EXTRACT_JS = r"""
(() => {
  const out = [];
  const vid = (h) => { const m = (h||'').match(/[?&]v=([^&]+)/); return m ? m[1] : null; };
  const push = (title, channel, dur, href) => {
    const id = vid(href);
    const url = id ? ('https://www.youtube.com/watch?v=' + id)
              : (href && href.startsWith('/') ? ('https://www.youtube.com' + href) : null);
    if (!url) return;
    out.push({ type: 'video', title: title || null, author: channel || null,
               url, meta: dur || null });
  };
  for (const r of document.querySelectorAll('ytd-playlist-video-renderer')) {
    const a = r.querySelector('a#video-title');
    const ch = r.querySelector('ytd-channel-name a');
    const dur = r.querySelector('ytd-thumbnail-overlay-time-status-renderer #text, #text.ytd-thumbnail-overlay-time-status-renderer, .badge-shape-wiz__text');
    push(a ? (a.getAttribute('title') || a.textContent.trim()) : null,
         ch ? ch.textContent.trim() : null,
         dur ? dur.textContent.trim() : null,
         a ? a.getAttribute('href') : null);
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
    push(a ? (a.getAttribute('title') || a.textContent.trim()) : null,
         ch ? ch.textContent.trim() : null, dur,
         a ? a.getAttribute('href') : null);
  }
  return out;
})()
"""

PLATFORM = Platform(
    key="youtube", name="YouTube", color="#FF0000", blurb="Watch Later & Liked",
    domain="youtube.com", auth_cookie="LOGIN_INFO",
    login_url="https://www.youtube.com",
    collections=(
        Collection(key="watch_later", name="Watch Later", kind="bookmarks",
                   url="https://www.youtube.com/playlist?list=WL", nav="scroll",
                   extract_js=_EXTRACT_JS, count_js=_COUNT_JS),
        Collection(key="liked", name="Liked videos", kind="likes",
                   url="https://www.youtube.com/playlist?list=LL", nav="scroll",
                   extract_js=_EXTRACT_JS, count_js=_COUNT_JS),
    ),
)
```

- [ ] **Step 4: Write `collector/platforms/reddit.py`**

```python
"""Reddit: Saved posts & comments (paginated old.reddit)."""
from collector.platforms.base import Collection, Platform

# old.reddit.com/saved auto-redirects to the logged-in user's saved page and
# paginates via a "next" button (server-rendered, no infinite scroll).
_EXTRACT_JS = r"""
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

_NEXT_JS = "(()=>{const a=document.querySelector('span.next-button a');return a?a.href:''})()"

PLATFORM = Platform(
    key="reddit", name="Reddit", color="#FF4500", blurb="Saved posts & comments",
    domain="reddit.com", auth_cookie="reddit_session",
    login_url="https://www.reddit.com/login",
    collections=(
        Collection(key="saved", name="Saved", kind="bookmarks",
                   url="https://old.reddit.com/saved", nav="paginate",
                   extract_js=_EXTRACT_JS, next_js=_NEXT_JS),
    ),
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_platform_modules.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add collector/platforms/youtube.py collector/platforms/reddit.py tests/test_platform_modules.py
git commit -m "feat: YouTube + Reddit platform modules on new contract"
```

---

### Task 4: Registry (`registry.py`)

**Files:**
- Create: `collector/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

`tests/test_registry.py`:

```python
from collector import registry


def test_registry_loads_known_platforms():
    keys = {p.key for p in registry.PLATFORMS}
    assert {"youtube", "reddit"} <= keys


def test_by_key_lookup():
    assert registry.BY_KEY["youtube"].name == "YouTube"


def test_every_platform_validates():
    from collector.platforms.base import validate_platform
    for p in registry.PLATFORMS:
        validate_platform(p)  # raises on malformed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'collector.registry'`.

- [ ] **Step 3: Write `collector/registry.py`**

```python
"""Discovers and validates all platform modules. Add a module name here (and
create collector/platforms/<name>.py with a PLATFORM) to register a platform."""
import importlib

from collector.platforms.base import validate_platform

# Plan B appends: twitter, pinterest, linkedin, instagram, tiktok, facebook
_MODULE_NAMES = ["youtube", "reddit"]


def load_platforms():
    plats = []
    for name in _MODULE_NAMES:
        mod = importlib.import_module(f"collector.platforms.{name}")
        validate_platform(mod.PLATFORM)
        plats.append(mod.PLATFORM)
    return plats


PLATFORMS = load_platforms()
BY_KEY = {p.key: p for p in PLATFORMS}


def label_map(platform):
    """{collection_key: human label} for one platform — used by storage + web."""
    return {c.key: c.name for c in platform.collections}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_registry.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add collector/registry.py tests/test_registry.py
git commit -m "feat: platform registry with validation"
```

---

### Task 5: Storage (`storage.py`)

**Files:**
- Create: `collector/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

`tests/test_storage.py`:

```python
import json
import os

from collector import storage


def test_dedup_by_collection_and_url():
    items = [
        {"collection": "a", "url": "u1", "title": "x"},
        {"collection": "a", "url": "u1", "title": "dup"},
        {"collection": "b", "url": "u1", "title": "other-collection"},
        {"collection": "a", "url": None, "title": "t-only"},
    ]
    out = storage.dedup(items)
    assert len(out) == 3  # the duplicate (a,u1) is dropped


def test_merge_replaces_only_crawled_collections():
    existing = [
        {"collection": "watch_later", "url": "wl1"},
        {"collection": "liked", "url": "lk1"},
    ]
    fresh = [{"collection": "liked", "url": "lk2"}]
    merged = storage.merge_collections(existing, fresh, ["liked"])
    cols = sorted((i["collection"], i["url"]) for i in merged)
    assert cols == [("liked", "lk2"), ("watch_later", "wl1")]


def test_save_writes_json_and_md(tmp_path):
    items = [{"collection": "saved", "type": "post", "title": "Hello",
              "author": "bob", "url": "https://x/1", "meta": ""}]
    storage.save(str(tmp_path), "reddit", items, {"saved": "Saved"})
    data = json.load(open(os.path.join(str(tmp_path), "reddit.json")))
    assert data[0]["title"] == "Hello"
    md = open(os.path.join(str(tmp_path), "reddit.md")).read()
    assert "Saved (1)" in md and "Hello" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_storage.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'collector.storage'`.

- [ ] **Step 3: Write `collector/storage.py`**

```python
"""File-based storage: atomic writes, dedup/merge, JSON + readable Markdown."""
import json
import os


def item_key(it):
    return (it.get("collection"), it.get("url") or it.get("title"))


def dedup(items):
    seen, out = set(), []
    for it in items:
        k = item_key(it)
        if k[1] is None or k in seen:
            if k[1] is None:
                out.append(it)  # keep url-less items (can't dedup), don't drop
            continue
        seen.add(k)
        out.append(it)
    return out


def merge_collections(existing, fresh, crawled_keys):
    """Keep on-disk items from collections we did NOT crawl; replace the crawled
    ones with freshly extracted items. Dedup the union."""
    crawled = set(crawled_keys)
    kept = [it for it in existing if it.get("collection") not in crawled]
    return dedup(kept + list(fresh))


def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def load_items(path):
    if not os.path.exists(path):
        return []
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return []


def render_md(platform_key, items, label_map):
    lines = [f"# {platform_key} saved ({len(items)} items)", ""]
    by = {}
    for it in items:
        by.setdefault(it.get("collection"), []).append(it)
    for coll, group in by.items():
        lines.append(f"## {label_map.get(coll, coll)} ({len(group)})\n")
        for i, x in enumerate(group, 1):
            lines.append(f"{i}. {x.get('title')} — {x.get('author') or '(none)'} — {x.get('url')}")
        lines.append("")
    return "\n".join(lines)


def save(data_dir, platform_key, items, label_map):
    os.makedirs(data_dir, exist_ok=True)
    atomic_write(os.path.join(data_dir, f"{platform_key}.json"),
                 json.dumps(items, ensure_ascii=False, indent=2))
    atomic_write(os.path.join(data_dir, f"{platform_key}.md"),
                 render_md(platform_key, items, label_map))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_storage.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add collector/storage.py tests/test_storage.py
git commit -m "feat: file storage with atomic write, dedup, collection merge"
```

---

### Task 6: Move `browser.py` and `cdp.py` into the package

**Files:**
- Move: `browser.py` → `collector/browser.py`
- Move: `cdp.py` → `collector/cdp.py`
- Test: `tests/test_imports.py`

- [ ] **Step 1: Move the files with git**

```bash
git mv browser.py collector/browser.py
git mv cdp.py collector/cdp.py
```

- [ ] **Step 2: Fix the import inside `collector/browser.py`**

In `collector/browser.py`, the `_all_cookies()` function imports cdp. Change the
line `import cdp` (inside `_all_cookies`) to:

```python
        from collector import cdp
```

Also change `from platforms import PLATFORMS` inside `platform_login_status()` to:

```python
    from collector.registry import PLATFORMS
```

And update `platform_login_status()` body to use attribute access (Platform is a
dataclass now, not a dict):

```python
def platform_login_status():
    """{platform_key: bool} for ALL platforms, from a single cookie read."""
    from collector.registry import PLATFORMS
    cookies = _all_cookies()
    out = {}
    for p in PLATFORMS:
        out[p.key] = any(n == p.auth_cookie and p.domain in d for n, d in cookies)
    return out
```

- [ ] **Step 3: Write the import smoke test**

`tests/test_imports.py`:

```python
def test_collector_package_imports():
    from collector import browser, cdp, registry, storage  # noqa: F401
    assert hasattr(browser, "ensure_headless")
    assert hasattr(cdp, "connect")
```

- [ ] **Step 4: Run the test**

Run: `python3 -m pytest tests/test_imports.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add collector/browser.py collector/cdp.py tests/test_imports.py
git commit -m "refactor: move browser + cdp into collector package"
```

---

### Task 7: Engine (`engine.py`)

**Files:**
- Create: `collector/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

`tests/test_engine.py`:

```python
from collector import engine
from collector.platforms.base import Collection


class FakeClient:
    """Routes evaluate() by matching the exact JS string the engine passes."""
    def __init__(self, heights, extract, next_urls=None, location="https://e.com/s"):
        self.sent = []
        self._heights = list(heights)
        self._extract = extract
        self._next = list(next_urls or [])
        self.location = location

    def send(self, method, params=None, timeout=30):
        # Records calls. Does NOT change `location` — `location` models where the
        # browser actually ENDS UP (which may differ from the navigated URL when a
        # site redirects to a login page). Set `location` via the constructor.
        self.sent.append((method, params))
        return {}

    def evaluate(self, expr, **kw):
        if "location.href" in expr:
            return self.location
        if expr == "PROBE":
            return self._heights.pop(0) if self._heights else 0
        if expr == "EXTRACT":
            return list(self._extract)
        if expr == "NEXT":
            return self._next.pop(0) if self._next else ""
        return None


def _scroll_collection():
    return Collection(key="saved", name="Saved", kind="bookmarks", url="https://e.com/s",
                      nav="scroll", extract_js="EXTRACT", count_js="PROBE")


def test_scroll_stops_when_probe_stabilizes():
    client = FakeClient(heights=[10, 20, 20, 20], extract=[{"url": "u1", "title": "t"}])
    raw = engine.crawl_collection(client, _scroll_collection(), "https://e.com/s",
                                  log=lambda m: None, sleep=lambda s: None)
    assert raw == [{"url": "u1", "title": "t"}]


def test_scroll_skips_when_on_login_page():
    client = FakeClient(heights=[10], extract=[{"url": "u1", "title": "t"}],
                        location="https://e.com/login")
    raw = engine.crawl_collection(client, _scroll_collection(), "https://e.com/s",
                                  log=lambda m: None, sleep=lambda s: None)
    assert raw == []


def test_paginate_follows_next_until_empty():
    col = Collection(key="saved", name="Saved", kind="bookmarks", url="https://e.com/s",
                     nav="paginate", extract_js="EXTRACT", next_js="NEXT")
    client = FakeClient(heights=[], extract=[{"url": "u1", "title": "t"}],
                        next_urls=["https://e.com/p2", ""])
    raw = engine.crawl_collection(client, col, "https://e.com/s",
                                  log=lambda m: None, sleep=lambda s: None)
    # two pages crawled (next returned a url once, then "")
    assert len(raw) == 2


def test_select_collections_defaults_to_first():
    from collector.platforms import youtube
    cols = engine.select_collections(youtube.PLATFORM, None)
    assert [c.key for c in cols] == ["watch_later"]


def test_select_collections_honours_request():
    from collector.platforms import youtube
    cols = engine.select_collections(youtube.PLATFORM, ["watch_later", "liked"])
    assert [c.key for c in cols] == ["watch_later", "liked"]


def test_select_collections_ignores_unknown_keys():
    from collector.platforms import youtube
    cols = engine.select_collections(youtube.PLATFORM, ["bogus"])
    assert [c.key for c in cols] == ["watch_later"]  # falls back to default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_engine.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'collector.engine'`.

- [ ] **Step 3: Write `collector/engine.py`**

```python
"""Generic crawl engine: runs any platform's collections against a live headless
Chrome via CDP. Orchestration (scroll/paginate, login detection, dedup, save) is
platform-agnostic; the platform module supplies URLs + extraction JS."""
import os
import random
import re
import time

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

_LOGIN_RE = re.compile(
    r"(accounts\.google\.com|/i/flow/login|/login|/signin|/sign_in|/sign-in|"
    r"/auth/login|/account/login|/onboarding|/checkpoint|/challenge|/authwall)", re.I)

_SCROLL_JS = ("(() => { window.scrollTo(0, document.documentElement.scrollHeight); "
              "return document.documentElement.scrollHeight; })()")


def _on_login(client):
    try:
        return bool(_LOGIN_RE.search(client.evaluate("location.href") or ""))
    except Exception:
        return False


def scroll_until_stall(client, probe_js, log, sleep=time.sleep,
                       max_rounds=80, stable_target=3):
    last, stable, rnd = object(), 0, 0
    while rnd < max_rounds and stable < stable_target:
        client.evaluate(_SCROLL_JS)
        sleep(random.uniform(2.0, 4.0))
        cur = client.evaluate(probe_js)
        stable = stable + 1 if cur == last else 0
        last = cur
        rnd += 1
        if rnd % 3 == 0:
            log(f"    scroll {rnd}: {cur} (stable {stable}/{stable_target})")


def crawl_collection(client, collection, url, log, sleep=time.sleep):
    """Navigate to `url`, run the nav strategy, return raw extracted items."""
    if collection.nav == "paginate":
        items, cur = [], url
        for page in range(50):
            client.send("Page.navigate", {"url": cur})
            sleep(3)
            if _on_login(client):
                log(f"[skip] {collection.key}: redirected to login.")
                break
            raw = client.evaluate(collection.extract_js) or []
            items.extend(raw)
            log(f"    page {page + 1}: +{len(raw)} (total {len(items)})")
            nxt = client.evaluate(collection.next_js)
            if not nxt:
                break
            cur = nxt
            sleep(random.uniform(2.0, 4.0))
        return items

    # scroll
    client.send("Page.navigate", {"url": url})
    sleep(6)
    if _on_login(client):
        log(f"[skip] {collection.key}: redirected to login.")
        return []
    probe = collection.count_js or _SCROLL_JS
    scroll_until_stall(client, probe, log, sleep=sleep)
    return client.evaluate(collection.extract_js) or []


def select_collections(platform, requested_keys):
    if not requested_keys:
        return [platform.default_collection]
    keys = set(requested_keys)
    chosen = [c for c in platform.collections if c.key in keys]
    return chosen or [platform.default_collection]


def _resolve_username(client, platform, log, sleep=time.sleep):
    client.send("Page.navigate", {"url": "https://www." + platform.domain})
    sleep(4)
    for _ in range(5):
        try:
            v = (client.evaluate(platform.username_js) or "").strip()
            if v:
                return v
        except Exception:
            pass
        sleep(2.5)
    return None


def run(platform_key, requested_keys=None, log=print, data_dir=DATA):
    """Full crawl for one platform. Returns 0 ok, non-zero on hard failure."""
    from collector import browser, cdp, storage
    from collector.registry import BY_KEY, label_map

    p = BY_KEY.get(platform_key)
    if not p:
        log(f"[error] unknown platform '{platform_key}'")
        return 2

    cols = select_collections(p, requested_keys)
    log(f"[*] {p.name}: ensuring headless browser…")
    browser.ensure_headless(p.login_url)
    if not browser.logged_in(p.auth_cookie, p.domain):
        log(f"[FAIL] not logged in to {p.name}. Click 'Log in' on its card.")
        return 3

    client, _ = cdp.connect(browser.cdp_host(), url_substr="")
    try:
        client.send("Network.setUserAgentOverride", {"userAgent": browser.NORMAL_UA})
    except Exception:
        pass

    username = None
    if p.needs_username:
        username = _resolve_username(client, p, log)
        if username:
            log(f"[*] resolved username: {username}")

    existing = storage.load_items(os.path.join(data_dir, f"{p.key}.json"))
    fresh, crawled = [], []
    try:
        for c in cols:
            url = c.url
            if "{username}" in url:
                if not username:
                    log(f"[skip] {c.key}: couldn't resolve username for {p.name}.")
                    continue
                url = url.format(username=username)
            log(f"[*] {p.name}/{c.name}: {url}")
            raw = crawl_collection(client, c, url, log)
            for it in raw:
                if not it.get("url"):
                    continue
                it["platform"] = p.key
                it["collection"] = c.key
                fresh.append(it)
            crawled.append(c.key)
            merged = storage.merge_collections(existing, fresh, crawled)
            storage.save(data_dir, p.key, merged, label_map(p))
            log(f"[=] {c.name}: collection done (running total {len(merged)})")
    finally:
        client.close()

    final = storage.load_items(os.path.join(data_dir, f"{p.key}.json"))
    log(f"\n[OK] {p.name}: {len(final)} items -> data/{p.key}.json")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_engine.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add collector/engine.py tests/test_engine.py
git commit -m "feat: generic crawl engine (scroll/paginate, login skip, merge save)"
```

---

### Task 8: Web app (`web/__init__.py`) on the engine

**Files:**
- Move: `llm.py` → `web/llm.py`
- Create: `web/__init__.py`
- Move: `templates/` → `web/templates/`, `static/` → `web/static/`
- Test: `tests/test_web.py`

- [ ] **Step 1: Move files**

```bash
mkdir -p web
git mv llm.py web/llm.py
git mv templates web/templates
git mv static web/static
```

- [ ] **Step 2: Write the failing test**

`tests/test_web.py`:

```python
import json

from web import app


def test_health_includes_collections():
    c = app.test_client()
    data = json.loads(c.get("/api/health").data)
    yt = next(p for p in data["platforms"] if p["key"] == "youtube")
    keys = [col["key"] for col in yt["collections"]]
    assert keys == ["watch_later", "liked"]
    assert yt["collections"][1]["kind"] == "likes"


def test_crawl_unknown_platform_404():
    c = app.test_client()
    r = c.post("/api/crawl/nope", json={"collections": ["saved"]})
    assert r.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_web.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'web'` (or no `app`).

- [ ] **Step 4: Write `web/__init__.py`**

```python
"""Flask dashboard for the headless saved-content collector.

Per-platform login + collection selection, in-process crawl via collector.engine,
serial crawl queue, file-based storage.
"""
import json
import os
import threading

from flask import Flask, jsonify, render_template, request

from collector import browser, engine, storage
from collector.registry import BY_KEY, PLATFORMS, label_map
from web.llm import get_client, load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE_DIR, "data")
load_dotenv()
app = Flask(__name__)

JOBS = {}
LOCK = threading.Lock()
RUNNING = {"key": None}


def load_items(key):
    return storage.load_items(os.path.join(DATA, f"{key}.json"))


def normalize(key, items):
    p = BY_KEY.get(key)
    labels = label_map(p) if p else {}
    out = []
    for it in items:
        coll = it.get("collection")
        group = it.get("subreddit") or labels.get(coll, coll)
        out.append({
            "platform": key, "type": it.get("type", "item"),
            "title": it.get("title"), "author": it.get("author"),
            "url": it.get("url"), "meta": it.get("meta") or it.get("duration") or "",
            "group": group, "collection": coll,
        })
    return out


def run_crawl(key, collection_keys):
    job = JOBS[key] = {"running": True, "log": [], "returncode": None}

    def add(line):
        with LOCK:
            job["log"].append(str(line).rstrip("\n"))
            if len(job["log"]) > 400:
                job["log"] = job["log"][-400:]

    try:
        rc = engine.run(key, collection_keys, log=add, data_dir=DATA)
        job["returncode"] = rc
    except Exception as e:  # noqa: BLE001
        add(f"[error] {e}")
        job["returncode"] = -1
    finally:
        job["running"] = False
        RUNNING["key"] = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    session = browser.status()
    try:
        login_status = browser.platform_login_status()
    except Exception:
        login_status = {}
    plats = []
    for p in PLATFORMS:
        j = JOBS.get(p.key)
        has_likes = any(c.kind == "likes" for c in p.collections)
        plats.append({
            "key": p.key, "name": p.name, "color": p.color, "blurb": p.blurb,
            "status": "solid" if p.key in ("youtube", "reddit") else "experimental",
            "built": True,
            "logged_in": login_status.get(p.key, False),
            "count": len(load_items(p.key)),
            "running": bool(j and j["running"]),
            "has_likes": has_likes,
            "collections": [{"key": c.key, "name": c.name, "kind": c.kind}
                            for c in p.collections],
        })
    return jsonify({"session": session, "platforms": plats, "busy": RUNNING["key"]})


@app.route("/api/login/<key>", methods=["POST"])
def api_login(key):
    p = BY_KEY.get(key)
    if not p:
        return jsonify({"error": "unknown"}), 404
    threading.Thread(target=browser.login, args=(p.login_url,), daemon=True).start()
    return jsonify({"status": "login_window_opening", "platform": key,
                    "message": f"A window is opening — sign in to {p.name} there."})


@app.route("/api/account/detect", methods=["POST"])
def api_detect():
    return jsonify({"account": browser.detect_account()})


@app.route("/api/crawl/<key>", methods=["POST"])
def api_crawl(key):
    p = BY_KEY.get(key)
    if not p:
        return jsonify({"error": "unknown platform"}), 404
    if not browser.logged_in(p.auth_cookie, p.domain):
        return jsonify({"error": "needs_login",
                        "message": f"Not logged in to {p.name}. Click 'Log in' on its card."}), 409
    body = request.get_json(silent=True) or {}
    requested = body.get("collections") or None
    valid = {c.key for c in p.collections}
    collection_keys = [k for k in (requested or []) if k in valid] or None
    with LOCK:
        if RUNNING["key"]:
            return jsonify({"error": "busy",
                            "message": f"A crawl is already running ({RUNNING['key']})."}), 409
        RUNNING["key"] = key
    threading.Thread(target=run_crawl, args=(key, collection_keys), daemon=True).start()
    return jsonify({"status": "started", "platform": key, "collections": collection_keys})


@app.route("/api/crawl/<key>/status")
def api_crawl_status(key):
    j = JOBS.get(key)
    if not j:
        return jsonify({"running": False, "log": [], "returncode": None})
    return jsonify({"running": j["running"], "returncode": j["returncode"], "log": j["log"][-200:]})


@app.route("/api/data")
def api_data():
    want = request.args.get("platform", "all")
    items = []
    for p in PLATFORMS:
        if want in ("all", p.key):
            items.extend(normalize(p.key, load_items(p.key)))
    return jsonify({"items": items, "count": len(items)})


@app.route("/api/summary", methods=["POST"])
def api_summary():
    body = request.get_json(silent=True) or {}
    sel = body.get("platforms")
    items = []
    for p in PLATFORMS:
        if not sel or p.key in sel:
            items.extend(normalize(p.key, load_items(p.key)))
    if not items:
        return jsonify({"error": "no_data", "message": "Nothing collected yet."}), 400
    compact = [{"platform": x["platform"], "title": x["title"], "by": x["author"], "group": x["group"]}
               for x in items]
    try:
        client, model = get_client()
    except RuntimeError as e:
        return jsonify({"error": "no_key", "message": str(e)}), 400
    prompt = ("Summarize this person's OWN saved content as concise markdown: a one-line overview, "
              "main themes (bullets), per-platform highlights, and 3 topic tags. Base everything ONLY "
              "on the data.\n\n" + json.dumps(compact, ensure_ascii=False))
    try:
        r = client.chat.completions.create(model=model, temperature=0.3, messages=[
            {"role": "system", "content": "You output clean markdown."},
            {"role": "user", "content": prompt}])
        return jsonify({"summary": r.choices[0].message.content, "model": model, "count": len(items)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": "llm_error", "message": str(e)}), 502
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_web.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add web/ tests/test_web.py
git commit -m "feat: web app on engine; collections in API + health"
```

---

### Task 9: Entry point `run.py` + port 5050

**Files:**
- Create: `run.py`
- Delete: `app.py`, `platforms.py`, `collect.py`, `collect_youtube.py`

- [ ] **Step 1: Create `run.py`**

```python
#!/usr/bin/env python3
"""Entry point: launch the headless saved-content dashboard."""
from web import app

if __name__ == "__main__":
    # Port 5050 (not 5000) — macOS AirPlay Receiver squats on 5000.
    print("Headless dashboard -> http://localhost:5050")
    app.run(host="127.0.0.1", port=5050, threaded=True)
```

- [ ] **Step 2: Delete the superseded top-level modules**

```bash
git rm app.py platforms.py collect.py collect_youtube.py
```

- [ ] **Step 3: Verify nothing imports the deleted modules**

Run: `grep -rn "import platforms\|import collect\|from platforms\|import app\b" --include=*.py collector web run.py tests`
Expected: no output (clean).

- [ ] **Step 4: Verify the app boots and serves health**

Run: `python3 -c "from web import app; c=app.test_client(); print(c.get('/api/health').status_code)"`
Expected: prints `200`.

- [ ] **Step 5: Commit**

```bash
git add run.py
git commit -m "feat: run.py entry point on port 5050; remove old modules"
```

---

### Task 10: Frontend — collection (Likes) toggles

**Files:**
- Modify: `web/static/app.js` (`renderCrawlCards`, `startCrawl`)

- [ ] **Step 1: Add collection checkboxes to each card**

In `web/static/app.js`, replace the `card.innerHTML = ...` template inside
`renderCrawlCards` (the block starting `card.innerHTML = \`` through its closing
`` `; ``) with this version, which renders a checkbox per collection (Likes off
by default, bookmarks checked + disabled so it always runs):

```javascript
    const cols = (p.collections || []);
    const collBoxes = cols.map((c) => {
      const isLikes = c.kind === "likes";
      return `<label class="coll-opt">
        <input type="checkbox" class="coll-cb" data-key="${p.key}" value="${c.key}"
          ${isLikes ? "" : "checked disabled"} />
        <span>${esc(c.name)}</span></label>`;
    }).join("");

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
      <div class="c-colls">${collBoxes}</div>
      <button class="btn primary pbtn" data-key="${p.key}" data-action="${action}" ${disabled ? "disabled" : ""}
        style="background:${needLogin ? 'var(--accent)' : bg}">${label}</button>
      <div class="c-status" id="cstatus-${p.key}"></div>`;
```

- [ ] **Step 2: Send the selected collections on crawl**

In `web/static/app.js`, replace the `startCrawl` function with:

```javascript
async function startCrawl(key) {
  const statusEl = $(`#cstatus-${key}`);
  const collections = $$(`.coll-cb[data-key="${key}"]`)
    .filter((cb) => cb.checked).map((cb) => cb.value);
  const r = await fetch(`/api/crawl/${key}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ collections }),
  });
  const j = await r.json();
  if (!r.ok) { statusEl.className = "c-status err"; statusEl.textContent = j.message || j.error; return; }
  statusEl.className = "c-status run"; statusEl.textContent = "Started…";
  openDrawer(key); pollStatus(key); refresh();
}
```

- [ ] **Step 3: Add minimal styles for the checkboxes**

Append to `web/static/style.css`:

```css
.c-colls { display: flex; flex-wrap: wrap; gap: 10px; margin: 8px 0 10px; }
.coll-opt { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--muted); cursor: pointer; }
.coll-opt input { accent-color: var(--accent); }
```

- [ ] **Step 4: Manually verify in the browser**

Run: `python3 run.py`, open http://localhost:5050. On the YouTube card, confirm
two checkboxes appear: "Watch Later" (checked, disabled) and "Liked videos"
(unchecked). Reddit shows only "Saved" (checked, disabled). Stop the server.
Expected: checkboxes render as described.

- [ ] **Step 5: Commit**

```bash
git add web/static/app.js web/static/style.css
git commit -m "feat: per-platform Likes opt-in checkboxes in dashboard"
```

---

### Task 11: Docs + setup updates

**Files:**
- Modify: `setup.sh`
- Modify: `README.md`

- [ ] **Step 1: Update launch command in `setup.sh`**

In `setup.sh`, replace the two occurrences of `python3 app.py` with `python3 run.py`,
and replace `open http://localhost:5000` with `open http://localhost:5050`.

- [ ] **Step 2: Update `README.md`**

In `README.md`: change the launch section from `python3 app.py` / `http://localhost:5000`
to `python3 run.py` / `http://localhost:5050`. In the "Files" table, replace the
`app.py`, `browser.py`, `platforms.py`, `collect_youtube.py`, `collect.py`, `cdp.py`,
`llm.py` rows with the new layout:

```markdown
| `run.py` | entry point (launches the web app) |
| `web/` | Flask dashboard (`__init__.py`, `templates/`, `static/`, `llm.py`) |
| `collector/` | engine package: `browser.py`, `cdp.py`, `engine.py`, `storage.py`, `registry.py` |
| `collector/platforms/` | one module per platform (URLs, auth cookie, collections, extractor JS) |
| `data/` | collected items (your "database") |
| `.profile/` | Chrome profile (logins) — large, git-ignored |
```

Add a line under "How it works": "Each platform can expose multiple **collections**
(e.g. Bookmarks + Likes); tick the Likes box on a card to also collect it."

- [ ] **Step 3: Verify references are consistent**

Run: `grep -rn "app.py\|localhost:5000\|5000" README.md setup.sh`
Expected: no output (all references updated).

- [ ] **Step 4: Commit**

```bash
git add setup.sh README.md
git commit -m "docs: update setup + README for new layout and port 5050"
```

---

### Task 12: Full integration verification (live)

**Files:** none (verification only).

- [ ] **Step 1: Run the full unit suite**

Run: `python3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Boot the app and log in to YouTube**

Run `python3 run.py`, open http://localhost:5050, click **Log in** on the YouTube
card, sign in once. The card dot turns green and the button becomes **Crawl**.

- [ ] **Step 3: Crawl YouTube Watch Later only (default)**

Leave "Liked videos" unchecked. Click **Crawl**. Watch the log drawer.
Expected: items accumulate; on completion `data/youtube.json` exists and items
have correct `title`, `author`, `url` (a `watch?v=` link), and `collection` ==
`"watch_later"`.

- [ ] **Step 4: Crawl YouTube with Liked enabled**

Tick "Liked videos", click **Crawl** again.
Expected: `data/youtube.json` now contains both `watch_later` and `liked` items
(Watch Later items preserved, Liked added). Verify in Results that both groups
show.

- [ ] **Step 5: Crawl Reddit**

Log in to Reddit, click **Crawl**.
Expected: log shows page-by-page progress; `data/reddit.json` items have correct
`title`, `subreddit`, `author`, real `reddit.com` permalink URLs.

- [ ] **Step 6: Confirm existing data still renders**

In the dashboard Results, confirm pre-existing items load and the platform filter
chips + search still work.

- [ ] **Step 7: Final commit (if any doc tweaks were needed during verification)**

```bash
git add -A
git commit -m "test: verify YouTube + Reddit crawl end-to-end on new engine" || echo "nothing to commit"
```

---

## Notes for Plan B (not implemented here)

Plan B adds one module per remaining platform (`twitter`, `pinterest`, `linkedin`,
`instagram`, `tiktok`, `facebook`), appends each name to `_MODULE_NAMES` in
`collector/registry.py`, and writes a per-platform `extract_js` verified against a
live logged-in run (capture an HTML fixture during that run to lock a regression
test). Collections per the spec's mapping table: Twitter (bookmarks + likes),
Reddit upvoted is already covered conceptually, Pinterest/LinkedIn/Facebook
bookmarks-only, Instagram/TikTok bookmarks + likes (best-effort). The `status`
field in `/api/health` currently hardcodes solid for youtube/reddit — Plan B
should move `status` onto the Platform dataclass so each platform declares its own.
