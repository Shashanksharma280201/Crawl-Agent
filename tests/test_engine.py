from collector import engine
from collector.platforms.base import Collection


class FakeClient:
    """Routes evaluate() by matching the exact JS string the engine passes."""
    def __init__(self, heights, extract, next_urls=None, location="https://e.com/s"):
        self.sent = []
        self._heights = list(heights)
        self._extract = extract
        self._next = list(next_urls or [])
        self.location = location

    def send(self, method, params=None, timeout=30):
        # Records calls. Does NOT change `location` — `location` models where the
        # browser actually ENDS UP (which may differ from the navigated URL when a
        # site redirects to a login page). Set `location` via the constructor.
        self.sent.append((method, params))
        return {}

    def evaluate(self, expr, **kw):
        if "location.href" in expr:
            return self.location
        if expr == "PROBE":
            return self._heights.pop(0) if self._heights else 0
        if expr == "EXTRACT":
            return list(self._extract)
        if expr == "NEXT":
            return self._next.pop(0) if self._next else ""
        return None


def _scroll_collection():
    return Collection(key="saved", name="Saved", kind="bookmarks", url="https://e.com/s",
                      nav="scroll", extract_js="EXTRACT", count_js="PROBE")


def test_scroll_stops_when_probe_stabilizes():
    client = FakeClient(heights=[10, 20, 20, 20], extract=[{"url": "u1", "title": "t"}])
    raw = engine.crawl_collection(client, _scroll_collection(), "https://e.com/s",
                                  log=lambda m: None, sleep=lambda s: None)
    assert raw == [{"url": "u1", "title": "t"}]


def test_scroll_skips_when_on_login_page():
    client = FakeClient(heights=[10], extract=[{"url": "u1", "title": "t"}],
                        location="https://e.com/login")
    raw = engine.crawl_collection(client, _scroll_collection(), "https://e.com/s",
                                  log=lambda m: None, sleep=lambda s: None)
    assert raw == []


def test_paginate_follows_next_until_empty():
    col = Collection(key="saved", name="Saved", kind="bookmarks", url="https://e.com/s",
                     nav="paginate", extract_js="EXTRACT", next_js="NEXT")
    client = FakeClient(heights=[], extract=[{"url": "u1", "title": "t"}],
                        next_urls=["https://e.com/p2", ""])
    raw = engine.crawl_collection(client, col, "https://e.com/s",
                                  log=lambda m: None, sleep=lambda s: None)
    # two pages crawled (next returned a url once, then "")
    assert len(raw) == 2


def test_select_collections_defaults_to_first():
    from collector.platforms import youtube
    cols = engine.select_collections(youtube.PLATFORM, None)
    assert [c.key for c in cols] == ["watch_later"]


def test_select_collections_honours_request():
    from collector.platforms import youtube
    cols = engine.select_collections(youtube.PLATFORM, ["watch_later", "liked"])
    assert [c.key for c in cols] == ["watch_later", "liked"]


def test_select_collections_ignores_unknown_keys():
    from collector.platforms import youtube
    cols = engine.select_collections(youtube.PLATFORM, ["bogus"])
    assert [c.key for c in cols] == ["watch_later"]  # falls back to default
