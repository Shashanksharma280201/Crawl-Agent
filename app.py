#!/usr/bin/env python3
"""Headless saved-content dashboard (all platforms).

Per-platform login + collection, controlled from the webpage. Serial crawl queue,
file-based storage. agent-browser runs Chrome headless; cdp does extraction.
"""
import json
import os
import subprocess
import sys
import threading

from flask import Flask, jsonify, render_template, request

import browser
import platforms as P
from llm import get_client, load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE_DIR, "data")
load_dotenv()
app = Flask(__name__)

JOBS = {}
LOCK = threading.Lock()
RUNNING = {"key": None}


def crawl_cmd(p):
    if p["collector"] == "collect_youtube.py":
        return [sys.executable, "-u", os.path.join(BASE_DIR, "collect_youtube.py")]
    return [sys.executable, "-u", os.path.join(BASE_DIR, "collect.py"), p["key"]]


def load_items(key):
    path = os.path.join(DATA, f"{key}.json")
    if not os.path.exists(path):
        return []
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return []


def normalize(key, items):
    labels = {"watch_later": "Watch Later", "liked": "Liked videos", "saved": "Saved"}
    out = []
    for it in items:
        coll = it.get("collection")
        group = it.get("subreddit") or labels.get(coll, coll)
        out.append({
            "platform": key, "type": it.get("type", "item"),
            "title": it.get("title"),
            "author": it.get("channel") or it.get("author"),
            "url": it.get("url"),
            "meta": it.get("duration") or it.get("meta") or "",
            "group": group,
        })
    return out


# ---------------- crawl runner (serial) ----------------
def run_crawl(key, cmd):
    job = JOBS[key] = {"running": True, "log": [], "returncode": None}

    def add(line):
        with LOCK:
            job["log"].append(line.rstrip("\n"))
            if len(job["log"]) > 400:
                job["log"] = job["log"][-400:]

    try:
        add("$ " + " ".join(os.path.basename(c) for c in cmd[1:]))
        proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            add(line)
        proc.wait()
        job["returncode"] = proc.returncode
    except Exception as e:  # noqa: BLE001
        add(f"[error] {e}")
        job["returncode"] = -1
    finally:
        job["running"] = False
        RUNNING["key"] = None


# ---------------- routes ----------------
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
    for p in P.PLATFORMS:
        j = JOBS.get(p["key"])
        plats.append({
            "key": p["key"], "name": p["name"], "color": p["color"], "blurb": p["blurb"],
            "status": p["status"],          # solid | experimental
            "built": True,
            "logged_in": login_status.get(p["key"], False),
            "count": len(load_items(p["key"])),
            "running": bool(j and j["running"]),
        })
    return jsonify({"session": session, "platforms": plats, "busy": RUNNING["key"]})


@app.route("/api/login/<key>", methods=["POST"])
def api_login(key):
    p = P.BY_KEY.get(key)
    if not p:
        return jsonify({"error": "unknown"}), 404
    threading.Thread(target=browser.login, args=(p["login_url"],), daemon=True).start()
    return jsonify({"status": "login_window_opening", "platform": key,
                    "message": f"A window is opening — sign in to {p['name']} there."})


@app.route("/api/account/detect", methods=["POST"])
def api_detect():
    return jsonify({"account": browser.detect_account()})


@app.route("/api/crawl/<key>", methods=["POST"])
def api_crawl(key):
    p = P.BY_KEY.get(key)
    if not p:
        return jsonify({"error": "unknown platform"}), 404
    if not browser.logged_in(p["auth_cookie"], p["domain"]):
        return jsonify({"error": "needs_login",
                        "message": f"Not logged in to {p['name']}. Click 'Log in' on its card."}), 409
    with LOCK:
        if RUNNING["key"]:
            return jsonify({"error": "busy",
                            "message": f"A crawl is already running ({RUNNING['key']})."}), 409
        RUNNING["key"] = key
    threading.Thread(target=run_crawl, args=(key, crawl_cmd(p)), daemon=True).start()
    return jsonify({"status": "started", "platform": key})


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
    for p in P.PLATFORMS:
        if want in ("all", p["key"]):
            items.extend(normalize(p["key"], load_items(p["key"])))
    return jsonify({"items": items, "count": len(items)})


@app.route("/api/summary", methods=["POST"])
def api_summary():
    body = request.get_json(silent=True) or {}
    sel = body.get("platforms")
    items = []
    for p in P.PLATFORMS:
        if not sel or p["key"] in sel:
            items.extend(normalize(p["key"], load_items(p["key"])))
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


if __name__ == "__main__":
    print("Headless dashboard -> http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, threaded=True)
