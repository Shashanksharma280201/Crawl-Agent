import json

from web import app


def test_health_includes_collections():
    c = app.test_client()
    data = json.loads(c.get("/api/health").data)
    yt = next(p for p in data["platforms"] if p["key"] == "youtube")
    keys = [col["key"] for col in yt["collections"]]
    assert keys == ["watch_later", "liked"]
    assert yt["collections"][1]["kind"] == "likes"


def test_crawl_unknown_platform_404():
    c = app.test_client()
    r = c.post("/api/crawl/nope", json={"collections": ["saved"]})
    assert r.status_code == 404
