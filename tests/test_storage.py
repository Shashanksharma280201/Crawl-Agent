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
