"""Browser/session manager for the headless collector.

ONE dedicated Chrome profile (this project), driven via agent-browser:
  - login()         : open a VISIBLE window so the user signs in once
  - ensure_headless(): make sure a headless, logged-in Chrome is up (relaunch if dead)
  - logged_in()     : cookie-based check (fast, no navigation)
  - status()        : {running, headless, logged_in, account, url}

Real Chrome binary + dedicated profile dir => Google login works and we never
lock the user's everyday Chrome. The CDP port is dynamic, so we always resolve it.
"""
import json
import os
import re
import shutil
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(BASE_DIR, ".profile")
DATA = os.path.join(BASE_DIR, "data")
SESSION_FILE = os.path.join(DATA, "session.json")
LOGIN_URL = "https://www.youtube.com"


def _find_chrome():
    """Locate the Chrome/Chromium binary (Linux + macOS). CHROME_BIN overrides."""
    env = os.environ.get("CHROME_BIN")
    if env and os.path.exists(env):
        return env
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",   # macOS
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/opt/google/chrome/chrome",                                      # Linux
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return "/opt/google/chrome/chrome"  # last-resort default


CHROME = _find_chrome()
# Anti-bot: hide the automation flag; pair with NORMAL_UA (set via CDP) to avoid
# the "HeadlessChrome" UA that sites like Reddit block.
CHROME_ARGS = "--disable-blink-features=AutomationControlled"
NORMAL_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")


# Singleton/lock files a crashed Chrome can leave behind, stranding the profile.
_LOCK_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")
_last_launch = [0.0]   # for relaunch pacing


def _run(args, timeout=90):
    try:
        return subprocess.run(["agent-browser"] + args, capture_output=True,
                              text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ""


def close():
    return _run(["close", "--all"])


def clear_stale_locks():
    """Remove leftover Singleton* locks IF no Chrome is using this profile.
    A stale lock makes the next launch fall back to a different/empty profile
    (the 'looks logged out but cookies are on disk' failure)."""
    if _our_chrome_cmdlines():
        return  # a Chrome is alive on our profile; don't yank its lock
    for name in _LOCK_FILES:
        try:
            os.remove(os.path.join(PROFILE, name))
        except OSError:
            pass


def _open(url, headed):
    # Pace relaunches so rapid back-to-back calls can't crash Chrome.
    gap = time.time() - _last_launch[0]
    if gap < 3:
        time.sleep(3 - gap)
    clear_stale_locks()
    args = ["open", url, "--executable-path", CHROME, "--profile", PROFILE,
            "--args", CHROME_ARGS]
    if headed:
        args.append("--headed")
    out = _run(args, timeout=120)
    _last_launch[0] = time.time()
    return out


def on_our_profile():
    """True if a live Chrome is using our dedicated profile dir (cross-platform)."""
    return bool(_our_chrome_cmdlines())


def _kill_our_chrome():
    """Kill only Chrome instances using our profile (won't touch the user's
    everyday Chrome). pkill -f exists on both Linux and macOS."""
    try:
        subprocess.run(["pkill", "-9", "-f", PROFILE], capture_output=True, timeout=10)
    except Exception:
        pass


def login(url=LOGIN_URL):
    """Open a VISIBLE window for one-time sign-in."""
    close()
    return _open(url, headed=True)


def cdp_host():
    m = re.search(r"://127\.0\.0\.1:(\d+)", _run(["get", "cdp-url"], timeout=20))
    return f"http://127.0.0.1:{m.group(1)}" if m else None


def is_running():
    return cdp_host() is not None


def _proc_cmdlines():
    """Full command-line strings of running processes (cross-platform via ps).
    Works on both Linux (procps) and macOS (BSD ps); avoids pgrep flags and
    /proc, which differ between the two."""
    for argv in (["ps", "-A", "-ww", "-o", "command="],   # Linux + recent macOS
                 ["ps", "axww", "-o", "command="]):        # BSD/macOS fallback
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=10).stdout
            if out.strip():
                return out.splitlines()
        except Exception:
            continue
    return []


def _our_chrome_cmdlines():
    """Command lines of Chrome processes using OUR dedicated profile."""
    return [l for l in _proc_cmdlines() if PROFILE in l]


def is_headless():
    return any("--headless" in l for l in _our_chrome_cmdlines())


def _all_cookies():
    """[(name, domain)] for every cookie in the profile, via CDP (page-independent)."""
    host = cdp_host()
    if not host:
        return []
    try:
        import cdp
        c, _ = cdp.connect(host, url_substr="")
        cookies = c.send("Network.getAllCookies", timeout=15).get("cookies", [])
        c.close()
        return [(ck.get("name"), ck.get("domain", "")) for ck in cookies]
    except Exception:
        return []


def logged_in(cookie="LOGIN_INFO", domain="youtube.com"):
    """True if the platform's auth cookie exists for its domain."""
    return any(n == cookie and domain in d for n, d in _all_cookies())


def platform_login_status():
    """{platform_key: bool} for ALL platforms, from a single cookie read."""
    from platforms import PLATFORMS
    cookies = _all_cookies()
    out = {}
    for p in PLATFORMS:
        out[p["key"]] = any(n == p["auth_cookie"] and p["domain"] in d for n, d in cookies)
    return out


def ensure_headless(url="https://www.youtube.com"):
    """Guarantee a HEALTHY headless Chrome on OUR profile is up.

    Healthy = running, headless, on our profile dir, and cookies actually loaded.
    If a prior crash stranded the profile (stale lock -> wrong profile -> 0
    cookies), this detects it and self-heals with one clean relaunch.
    """
    # Healthy = running, headless, and our session cookies are actually loaded.
    # cookies>0 is the robust "right profile" signal: a stranded/empty profile
    # has 0 cookies, ours has many. (Avoids fragile cmdline matching that could
    # false-negative and trigger needless relaunches.)
    def healthy():
        return is_running() and is_headless() and len(_all_cookies()) > 0

    if healthy():
        return cdp_host()

    # Relaunch cleanly (up to 2 attempts): kill, clear locks, reopen, verify.
    for _ in range(2):
        close()
        time.sleep(1)
        _kill_our_chrome()
        time.sleep(2)
        clear_stale_locks()
        _open(url, headed=False)
        time.sleep(6)
        if is_running() and len(_all_cookies()) > 0:
            return cdp_host()
    return cdp_host()


# ---- account cache ----
def _load():
    try:
        return json.load(open(SESSION_FILE))
    except Exception:
        return {}


def _save(d):
    os.makedirs(DATA, exist_ok=True)
    json.dump(d, open(SESSION_FILE, "w"))


def account():
    return _load().get("account")


def detect_account():
    """Navigate to /account, grab the email, cache it. Call after login (safe
    when no crawl is running)."""
    if not is_running() or not logged_in():
        return account()
    _run(["open", "https://www.youtube.com/account"], timeout=60)
    time.sleep(3)
    email = _run(["eval", "(()=>{const m=document.body.innerText.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+/);return m?m[0]:''})()"]).strip().strip('"')
    if "@" in email:
        s = _load()
        s["account"] = email
        _save(s)
        return email
    return account()


def status():
    running = is_running()
    li = logged_in() if running else False
    return {
        "running": running,
        "headless": is_headless() if running else None,
        "logged_in": li,
        "account": account(),
        "url": _run(["get", "url"], timeout=20).strip() if running else None,
    }


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "login":
        print(login())
    elif cmd == "headless":
        print(ensure_headless())
    elif cmd == "account":
        print(detect_account())
    elif cmd == "close":
        print(close())
    else:
        print(json.dumps(status(), indent=2))
