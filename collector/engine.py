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
