"""Flask dashboard for the headless saved-content collector.

Per-platform login + collection selection, in-process crawl via collector.engine,
serial crawl queue, file-based storage.
"""
import json
import os
import re
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


def item_image(key, it):
    """Preview thumbnail URL for an item, or None.

    YouTube: derived from the video id in the watch URL (no stored field needed).
    Others: a real http(s) `thumbnail` captured by the extractor, else None.
    """
    if key == "youtube":
        m = re.search(r"[?&]v=([\w-]+)", it.get("url") or "")
        return f"https://i.ytimg.com/vi/{m.group(1)}/mqdefault.jpg" if m else None
    thumb = it.get("thumbnail")
    return thumb if (thumb and thumb.startswith("http")) else None


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
            "image": item_image(key, it),
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
