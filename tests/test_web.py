import json

from web import app, normalize


def test_normalize_image_youtube_from_video_id():
    out = normalize("youtube", [{"collection": "liked",
                                  "url": "https://www.youtube.com/watch?v=ABC123_x&t=5"}])
    assert out[0]["image"] == "https://i.ytimg.com/vi/ABC123_x/mqdefault.jpg"


def test_normalize_image_reddit_passthrough():
    out = normalize("reddit", [{"collection": "saved", "url": "https://r/1",
                                "thumbnail": "https://b.thumbs.redditmedia.com/x.jpg"}])
    assert out[0]["image"] == "https://b.thumbs.redditmedia.com/x.jpg"


def test_normalize_image_reddit_none_when_no_thumbnail():
    out = normalize("reddit", [{"collection": "saved", "url": "https://r/1"}])
    assert out[0]["image"] is None


def test_normalize_image_none_for_other_platform():
    out = normalize("twitter", [{"collection": "bookmarks", "url": "https://x/1"}])
    assert out[0]["image"] is None


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
