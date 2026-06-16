from collector.platforms import youtube, reddit
from collector.platforms.base import validate_platform


def test_youtube_has_two_collections_with_likes():
    p = youtube.PLATFORM
    validate_platform(p)
    keys = [c.key for c in p.collections]
    assert keys == ["watch_later", "liked"]
    assert p.collections[1].kind == "likes"


def test_reddit_saved_paginates():
    p = reddit.PLATFORM
    validate_platform(p)
    assert p.collections[0].key == "saved"
    assert p.collections[0].nav == "paginate"
    assert p.collections[0].next_js
