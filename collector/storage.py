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
