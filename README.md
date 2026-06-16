# Saved-Content Collector (headless)

Collect **your own saved content** from social platforms into local files, driven
from a simple web dashboard. The browser runs **headless** (no window) after a
one-time login per platform.

- **Solid:** YouTube (Watch Later + Liked), Reddit (saved)
- **Working / experimental:** X-Twitter (bookmarks), Pinterest (pins)
- **Experimental, code present:** Instagram, LinkedIn, TikTok, Facebook
- **Storage:** plain JSON/Markdown files in `data/` — no database needed

---

**Works on Linux and macOS.**

## 1. Prerequisites

| Need | Why |
|---|---|
| **Python 3.8+** | runs the app + collectors |
| **agent-browser** | headless browser driver — installed by `setup.sh` (via `npm i -g agent-browser`, or `brew install agent-browser` on macOS) |
| **Google Chrome** | the browser that gets driven (headless) |

**macOS notes:**
- Chrome is auto-detected at `/Applications/Google Chrome.app/...` (no config needed).
- Install agent-browser with **`brew install agent-browser`** if you don't use npm.
- The process/profile management is cross-platform (uses `ps`, not Linux-only `/proc`).

---

## 2. Setup (one command)

```bash
cd saved-collector-headless
bash setup.sh
```

This installs the Python packages (`flask`, `websocket-client`, `openai`),
installs **agent-browser**, finds your Chrome, and prepares `.env`.

> If Chrome isn't at the default path, `setup.sh` prints the line to run, e.g.
> `export CHROME_BIN="/usr/bin/google-chrome"`.

**(Optional)** For the "Summarize with AI" button, put an OpenAI key in `.env`:
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

---

## 3. Launch

```bash
python3 app.py
```
Open **http://localhost:5000**.

---

## 4. Use it

1. **Log in (once per platform).** Each platform card has a **Log in** button.
   Click it → a **visible Chrome window opens** → sign in there. The dot turns
   green and the button becomes **Crawl**. The login is saved, so future crawls
   run **headless** (no window).
2. **Crawl.** Click **Crawl** on a logged-in platform. A live log shows progress;
   when it finishes, the items appear in **Results**.
3. **Browse / filter / search** the collected items. Use the platform chips to
   filter (multi-select).
4. **Summarize with AI** (optional) — needs the OpenAI key in `.env`.

---

## 5. Where the data lives

```
data/youtube.json    data/youtube.md
data/reddit.json     data/reddit.md
data/twitter.json    data/twitter.md
data/pinterest.json  ...
data/session.json    (cached account name)
```
The `.json` files are the structured store; the `.md` files are readable lists.

---

## 6. How it works (short)

- `agent-browser` runs **headless Chrome** on a dedicated profile (`.profile/`),
  so your everyday Chrome is never touched and logins persist between runs.
- `cdp.py` talks to that Chrome (Chrome DevTools Protocol) to scroll + extract.
- `browser.py` manages the browser (launch, per-platform login detection,
  crash self-healing). `collect_youtube.py` / `collect.py` do the collection.
- Anti-bot: a normal User-Agent + `--disable-blink-features=AutomationControlled`
  so sites (e.g. Reddit) don't block the headless browser.
- **No MCP, no cloud** — just local programs driving your own browser.

---

## 7. Files

| File | Role |
|---|---|
| `app.py` | Flask web dashboard |
| `browser.py` | headless browser + session manager |
| `platforms.py` | per-platform registry (URLs, auth cookies, extractor) |
| `collect_youtube.py` | YouTube collector |
| `collect.py` | Reddit + generic collector (all other platforms) |
| `cdp.py` | Chrome DevTools client |
| `llm.py` | OpenAI helper (summary) |
| `templates/`, `static/` | dashboard UI |
| `data/` | collected items (your "database") |
| `.profile/` | Chrome profile (logins) — large, git-ignored |

---

## 8. Notes & limits

- **Experimental platforms** (Instagram/LinkedIn/TikTok/Facebook) use a generic
  accessibility-tree extractor — results vary and may need tuning; some have
  aggressive anti-bot that can degrade headless scraping.
- **One crawl at a time** (serial queue) — by design, on one browser.
- If a crawl says **"not logged in,"** click that platform's **Log in** again.
