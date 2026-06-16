"""Minimal Chrome DevTools Protocol client over websockets.

Connects to an already-running Chrome started with --remote-debugging-port.
No heavy framework: just requests-style HTTP for discovery + websocket for CDP.
"""
import json
import re
import time
import urllib.request
from urllib.parse import urlparse

import websocket  # websocket-client

# URLs that indicate we're sitting on a login / auth / account-chooser screen.
LOGIN_URL_RE = re.compile(
    r"(accounts\.google\.com|/i/flow/login|/login|/signin|/sign_in|/sign-in|"
    r"/auth/login|/account/login|/onboarding|/checkpoint|/challenge|/authwall)",
    re.I,
)


class CDPError(RuntimeError):
    pass


def _http_get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


class CDPClient:
    def __init__(self, ws_url, timeout=30):
        # suppress_origin avoids Chrome's 403 "Rejected ... from origin" handshake error.
        self.ws = websocket.create_connection(
            ws_url, max_size=None, timeout=timeout, suppress_origin=True
        )
        self._id = 0

    def send(self, method, params=None, timeout=30):
        """Send a CDP command and wait for the matching response id."""
        self._id += 1
        msg_id = self._id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(1, deadline - time.time()))
            try:
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                continue
            data = json.loads(raw)
            if data.get("id") == msg_id:
                if "error" in data:
                    raise CDPError(f"{method}: {data['error']}")
                return data.get("result", {})
            # ignore events / other ids
        raise CDPError(f"Timed out waiting for response to {method}")

    def evaluate(self, expression, await_promise=True, timeout=30):
        """Runtime.evaluate, returning the JS value (deep-serialized via JSON)."""
        res = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
            timeout=timeout,
        )
        if res.get("exceptionDetails"):
            raise CDPError(f"JS exception: {res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def find_page_target(debug_host="http://localhost:9222", url_substr=None):
    """Return the websocket debugger URL for a matching page target."""
    targets = _http_get_json(f"{debug_host}/json")
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if url_substr:
        for t in pages:
            if url_substr in (t.get("url") or ""):
                return t["webSocketDebuggerUrl"], t["url"]
    if not pages:
        raise CDPError("No page targets found in Chrome")
    return pages[0]["webSocketDebuggerUrl"], pages[0]["url"]


def connect(debug_host="http://localhost:9222", url_substr=None):
    ws_url, page_url = find_page_target(debug_host, url_substr)
    client = CDPClient(ws_url)
    # Enable the domains we use.
    client.send("Page.enable")
    client.send("Runtime.enable")
    return client, page_url


def wait_for_login(client, target_url, ready_js, timeout=300, poll=3.0, label="the platform"):
    """Wait until the user is logged in and the target content is ready.

    `ready_js` is a JS expression returning true ONLY when the logged-in target
    page has loaded (e.g. its feed/content container exists and we're not on a
    login URL). While the page sits on a login/auth screen we wait passively for
    the user to sign in; once they're off the login screen but not yet on the
    target, we (re)load the target URL. Returns True when ready, False on timeout.
    """
    deadline = time.time() + timeout
    announced = False
    try:
        target_path = urlparse(target_url).path or "/"
    except Exception:
        target_path = "/"

    while time.time() < deadline:
        try:
            if client.evaluate(ready_js):
                if announced:
                    print(f"[login] {label}: logged in — continuing.", flush=True)
                return True
        except Exception:
            pass
        try:
            href = client.evaluate("location.href") or ""
        except Exception:
            href = ""

        if LOGIN_URL_RE.search(href):
            if not announced:
                print(f"[login] Please log in to {label} in the opened Chrome tab. "
                      f"Waiting up to {int(timeout)}s for you to finish…", flush=True)
                announced = True
            time.sleep(poll)
        elif href and target_path != "/" and target_path not in href:
            # Off the login screen but not on the target page yet → load it.
            try:
                client.send("Page.navigate", {"url": target_url})
            except Exception:
                pass
            time.sleep(4)
        else:
            if not announced:
                print(f"[login] Waiting for {label} to be ready…", flush=True)
            time.sleep(poll)

    print(f"[login] Timed out after {int(timeout)}s waiting for {label} login.", flush=True)
    return False


def close_target(target_id, debug_host="http://localhost:9222"):
    """Close a tab by target id (best-effort)."""
    if not target_id:
        return
    try:
        ver = _http_get_json(f"{debug_host}/json/version")
        ws = websocket.create_connection(ver["webSocketDebuggerUrl"],
                                         suppress_origin=True, max_size=None)
        try:
            ws.send(json.dumps({"id": 1, "method": "Target.closeTarget",
                                "params": {"targetId": target_id}}))
            for _ in range(20):
                if json.loads(ws.recv()).get("id") == 1:
                    break
        finally:
            ws.close()
    except Exception:
        pass


def open_page(url, debug_host="http://localhost:9222", wait=2.0):
    """Open a brand-new tab at `url` via the browser endpoint and return a
    connected CDPClient for it. Used to collect a site that isn't open yet."""
    ver = _http_get_json(f"{debug_host}/json/version")
    bws = ver["webSocketDebuggerUrl"]
    ws = websocket.create_connection(bws, suppress_origin=True, max_size=None)
    try:
        ws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                            "params": {"url": url}}))
        target_id = None
        for _ in range(60):
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                target_id = msg["result"]["targetId"]
                break
    finally:
        ws.close()
    if not target_id:
        raise CDPError("Failed to create target tab")
    # Find the page target's websocket URL.
    page_ws = None
    deadline = time.time() + 10
    while time.time() < deadline:
        for t in _http_get_json(f"{debug_host}/json"):
            if t.get("id") == target_id and t.get("webSocketDebuggerUrl"):
                page_ws = t["webSocketDebuggerUrl"]
                break
        if page_ws:
            break
        time.sleep(0.3)
    if not page_ws:
        raise CDPError("Created tab but could not find its websocket")
    client = CDPClient(page_ws)
    client.send("Page.enable")
    client.send("Runtime.enable")
    time.sleep(wait)
    return client, target_id
