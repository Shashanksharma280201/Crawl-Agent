# Multi-Platform Saved-Content Extractors — Design

**Date:** 2026-06-16
**Status:** Approved (pending spec review)

## Problem

The headless collector works well for YouTube (4430 items, correct fields) and
Reddit (purpose-built extractors). Every other platform falls through to a
single generic accessibility-tree extractor (`extract_generic` in `collect.py`),
which produces wrong data:

- **Twitter** — captures sidebar nav ("Notifications", "Direct Messages") and
  analytics sub-links instead of bookmarked tweets.
- **LinkedIn** — titles are embedded-image alt-text ("Image preview"), no author.
- **Pinterest** — titles polluted with "pin page" suffix, many "Untitled", no author.
- The generic path has **no author, no post text, no timestamp**, and is not
  scoped to the real content container.

Two root causes:
1. **One weak generic extractor** reads Chrome's a11y text dump and grabs link
   accessibility labels — the wrong data. It cannot be tuned into correctness.
2. **No model for multiple collections per platform.** Each platform has a single
   `saved_url`; only YouTube has multiple collections (Watch Later + Liked),
   hardcoded in its collector. So "Likes/Favorites" lists are unreachable for
   every other platform.

## Goals

- Every platform extracts **correct, structured data** (title, author, url, type,
  timestamp) via a **per-platform DOM extractor** run through CDP
  `Runtime.evaluate` — the proven YouTube/Reddit method.
- Support **multiple collections per platform** (Bookmarks/Saved + Likes/Favorites
  where they exist).
- The **web UI lets the user opt in to Likes per platform**, shown only for
  platforms that actually have a Likes list.
- Improve the **directory structure** into a clean Python package.
- Delete the broken generic a11y extractor entirely.

## Non-Goals (this round)

- Custom/manual bookmarks store.
- Periodic / scheduled auto-refresh.
- API-based ingestion (Pocket, Raindrop, browser bookmarks).

## Collection Mapping

Each platform declares one or more **collections**. The first is the default
(always available); a `likes`-kind collection is optional and surfaced as a UI
toggle.

| Platform   | Default collection        | Optional (Likes) collection            | Notes |
|------------|---------------------------|----------------------------------------|-------|
| YouTube    | `watch_later` (Watch Later) | `liked` (Liked videos)               | Already works; both keep current extractors |
| Twitter/X  | `bookmarks` (`/i/bookmarks`) | `likes` (`/<user>/likes`)            | Likes needs username resolution |
| Reddit     | `saved` (`old.reddit.com/saved`) | `upvoted` (`/user/<user>/upvoted`) | Upvoted often private — best-effort |
| Instagram  | `saved` (`/<user>/saved/`)  | `liked` (activity → likes)            | Heavy anti-bot — best-effort |
| TikTok     | `favorites` (profile tab)   | `liked` (profile tab)                 | Liked tab usually private — best-effort |
| Pinterest  | `saved` (`/<user>/_saved/`) | — (likes deprecated)                  | No likes toggle |
| LinkedIn   | `saved` (`/my-items/saved-posts/`) | — (no likes list)              | No likes toggle |
| Facebook   | `saved` (`/saved`)          | — (no clean likes list)               | No likes toggle |

**Feasibility honesty:** YouTube, Twitter, Reddit, Pinterest, LinkedIn are
expected to stay solid. Instagram, TikTok, Facebook have aggressive anti-bot and
frequently-changing obfuscated HTML — their extractors are best-effort and will
need periodic re-tuning. The architecture isolates each so re-tuning touches one
file.

## Architecture

Approach: **plugin registry + generic engine.** Each platform is a small module
declaring metadata + collections + DOM-extraction JS + nav style. A single engine
runs the repetitive crawl loop for all of them.

```
web (Flask) ──▶ collector.engine.run(platform_key, collection_keys)
                    │
                    ├─ browser.ensure_headless() + login check
                    └─ for each requested collection:
                         navigate → scroll/paginate → CDP Runtime.evaluate(extract_js)
                         → normalize → dedup → atomic save (incremental)
                    ▼
                data/<platform>.json  +  data/<platform>.md
```

### Directory structure

```
saved-collector/
├── run.py                  # entry point — launches the web app (was app.py)
├── requirements.txt
├── setup.sh
├── README.md
├── collector/              # engine package
│   ├── __init__.py
│   ├── browser.py          # headless Chrome / session mgmt (moved, ~unchanged)
│   ├── cdp.py              # DevTools client (moved, unchanged)
│   ├── engine.py           # generic crawl loop + nav strategies
│   ├── storage.py          # atomic write, dedup, normalize, .md rendering
│   ├── registry.py         # discovers/loads all platform modules
│   └── platforms/
│       ├── __init__.py
│       ├── base.py         # Platform/Collection dataclasses + shared JS helpers
│       ├── youtube.py
│       ├── reddit.py
│       ├── twitter.py
│       ├── pinterest.py
│       ├── linkedin.py
│       ├── instagram.py
│       ├── tiktok.py
│       └── facebook.py
├── web/
│   ├── __init__.py         # Flask app + routes (was app.py)
│   ├── llm.py              # OpenAI helper (moved)
│   ├── templates/index.html
│   └── static/{app.js, style.css}
├── data/                   # data/<platform>.json + .md (unchanged location)
└── .profile/               # Chrome profile (unchanged)
```

### Platform module contract

Each platform module exposes a `PLATFORM` object with:

- **Metadata:** `key`, `name`, `color`, `blurb`, `domain`, `auth_cookie`,
  `login_url`.
- **`needs_username`:** bool — whether collection URLs require the logged-in
  username resolved at runtime.
- **`username_js`:** optional JS expression to resolve the username (only if
  `needs_username`).
- **`collections`:** ordered list of Collection objects, each with:
  - `key` (e.g. `bookmarks`, `likes`), `name` (UI label), `kind`
    (`bookmarks` | `likes`),
  - `url` (may contain `{username}`),
  - `nav` (`scroll` | `paginate`),
  - `extract_js` (JS returning an array of raw item objects), and for
    `paginate`: `next_js` (JS returning the next-page URL or "").

The default/first collection has `kind: bookmarks` (or the platform's primary
saved list); `kind: likes` collections are optional.

### Engine responsibilities (`engine.py`)

1. `browser.ensure_headless(login_url)` and login check via `auth_cookie`/`domain`.
2. Set normal User-Agent override (anti-bot), as today.
3. Resolve username once if `needs_username`.
4. For each requested collection:
   - Navigate to its URL; bail with a clear message if redirected to login.
   - Run the nav strategy: `scroll` = scroll-until-stall; `paginate` = follow
     `next_js` page by page.
   - Run `extract_js` via `cdp.Runtime.evaluate`.
   - Normalize + dedup (by stable id/url) and **atomic incremental save** after
     each collection, merging across collections into one
     `data/<platform>.json`.
5. Print structured progress + final counts per collection (surfaced in UI log).

### Storage (`storage.py`)

- One file per platform: `data/<platform>.json` (list) + `.md` (readable).
- Each item carries `platform`, `collection`, `type`, `title`, `author`, `url`,
  optional `meta`/`timestamp`/`body`.
- Atomic writes (`.tmp` → `os.replace`), dedup by `(collection, id-or-url)`.
- Crawling a subset of collections **preserves** items from other collections
  already on disk (merge, don't clobber).

## Web UI changes

- **Platform card** renders its collections as checkboxes:
  - default/bookmarks collection checked and (effectively) always run,
  - each `likes`-kind collection rendered as an opt-in checkbox, **off by
    default**; cards with no likes collection show no toggle.
- **Crawl** sends `POST /api/crawl/<key>` with body
  `{ "collections": ["bookmarks", "likes"] }`. If body omitted/empty, the engine
  runs only the default collection.
- `/api/health` includes each platform's collection definitions so the frontend
  can render the right checkboxes.
- Results view unchanged in shape; items already carry `collection`, so Bookmarks
  vs Likes are distinguishable. `group` in `normalize` maps collection keys to
  readable labels.

## Error handling

- **Not logged in** → engine returns a distinct code; UI shows red "Log in"
  (existing behavior preserved).
- **Redirected to login mid-collection** → log clear message, skip that
  collection, continue others.
- **Username unresolved** (needs_username platforms) → skip collections that
  require it, with a clear log line; don't crash the whole crawl.
- **Anti-bot block** (e.g. Reddit "blocked by network security") → log and stop
  that collection.
- **Extractor returns 0 items** → save nothing for that collection but log it
  (distinguish "genuinely empty" from "broken" where possible).
- Partial success is fine: a crawl over 2 collections saves whatever each yields.

## Testing strategy

- **Unit (no browser):** `storage` dedup/merge/atomic-write; `normalize`
  collection→label mapping; registry loads all platform modules and each declares
  a valid contract (keys unique, default collection present, likes collections
  marked).
- **Extractor JS (offline):** save real saved-page HTML fixtures per platform and
  run each `extract_js` against the fixture DOM (via a headless eval or jsdom-style
  check) asserting correct title/author/url. Start with YouTube + Reddit (known
  good) to lock the harness, then add fixtures per platform as extractors are
  built.
- **Manual/integration:** logged-in run per platform, eyeball counts and a few
  items; verify Bookmarks vs Likes land under the right `collection`.
- **Migration sanity:** existing `data/youtube.json` (4430) still loads and the
  dashboard renders after the restructure.

## Migration / compatibility

- `app.py` → `run.py` + `web/__init__.py`; update `setup.sh`/README launch command.
- `browser.py`, `cdp.py`, `llm.py` move into packages; update imports. Behavior
  unchanged.
- Data files keep their location and shape; YouTube data carries over untouched.
- Port: also switch default Flask port off 5000 (macOS AirPlay conflict) — use
  5050 — and update README/setup references. (Small, in-scope quality fix.)

## Open questions

None blocking. Per-platform DOM selectors will be finalized against live pages
during implementation (they change over time); the architecture isolates that
churn to single files.
