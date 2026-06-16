# Headless + Reliable Saved-Content Collector — Plan

## Goal
Collect a user's own saved content (YouTube first) **fully headless** after a
one-time login, **reliably** (survive crashes / port changes / session loss;
never lose data; fail loudly), with an **`app.py`-style webapp**.

## Locked decisions
| Decision | Choice |
|---|---|
| Account | `Shashank@flomobility.com` (dedicated project profile) |
| Profile | Dedicated dir `./.profile` (real Chrome binary) — never touches daily Chrome |
| Extraction | **Hybrid** — agent-browser runs headless browser + login; **cdp eval** extracts (fast, O(1), scales) |
| Concurrency | **Serial queue** — one crawl at a time on one headless browser |
| Storage | File-based: `data/<platform>.json` + `.md`, atomic writes |
| Mode | Headless after one-time headed login |

## Architecture
```
Flask webapp ──┬─▶ Browser Manager ─▶ agent-browser daemon ─▶ headless Chrome (.profile)
               └─▶ Collectors (cdp eval against that Chrome) ─▶ data/<platform>.json/.md
```

## Components
1. **Browser Manager** (`browser.py`) — keep ONE headless Chrome alive; re-resolve
   the dynamic CDP port before every op; relaunch if dead; `login()` / `status()` / `headless()`.
2. **Collectors** (`collect_<platform>.py`) — navigate → scroll-until-stall →
   **cdp eval extract** → incremental + atomic save → resumable.
3. **Webapp** (`app.py`) — dashboard + login flow + queued crawl jobs + live logs + data + AI summary.
4. **Storage** — `data/` json+md, `.tmp`→`os.replace()` atomic, `.partial.json` for resume.

## Reliability mechanisms (failure → fix)
| Failure observed | Fix |
|---|---|
| Browser restarted, port changed | Re-resolve CDP port every op; health-check + auto-relaunch |
| Crash mid-run lost all data | Incremental + atomic save, dedup by id, **resume** |
| Silent buffered failure | Flushed structured logs + exit codes surfaced in UI |
| Session expired (headless can't re-login) | `status()` detects → stop fast → UI shows red **Log in** |
| Snapshot OOM/slow at scale | Hybrid cdp extract (O(1)); per-call timeouts; stall detection |
| Concurrent crawls collide | Serial queue + lock |
| Idle daemon shutdown | Manager relaunches on demand |
| Layout gaps (missing channel) | Per-layout parse + optional oembed backfill |

## Webapp
- States: `browser down` · `needs login` · `ready (account)` · `crawling`
- Endpoints: `/api/health`, `/api/login`, `/api/crawl/<p>`, `/api/crawl/<p>/status`, `/api/data`, `/api/summary`
- Buttons: Log in (headed once) · Crawl (queued background) · Summarize with AI
- Multi-select platform filter + file-based data view (from old app.py)

## Build order
1. ✅ Session layer — login headed → headless reuse, account locked
2. ☐ Browser Manager hardening — port re-resolve, health-check, auto-relaunch, keep-alive
3. ☐ Reliable collector — cdp hybrid extract + incremental/atomic save + resume + timeouts
4. ☐ Flask webapp — login flow, queued jobs, live logs, data, summary
5. ☐ Polish — oembed backfill, AI summary, multi-platform stubs
