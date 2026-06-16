from collector import registry


ALL_KEYS = {"youtube", "reddit", "twitter", "pinterest", "linkedin",
            "instagram", "tiktok", "facebook"}


def test_registry_loads_all_platforms():
    keys = {p.key for p in registry.PLATFORMS}
    assert keys == ALL_KEYS


def test_platforms_with_likes_have_a_likes_collection():
    for key in ("youtube", "twitter", "instagram", "tiktok"):
        p = registry.BY_KEY[key]
        kinds = {c.kind for c in p.collections}
        assert "likes" in kinds, f"{key} should expose a likes collection"


def test_username_platforms_declare_username_js():
    for key in ("twitter", "pinterest", "instagram", "tiktok"):
        p = registry.BY_KEY[key]
        assert p.needs_username and p.username_js


def test_by_key_lookup():
    assert registry.BY_KEY["youtube"].name == "YouTube"


def test_every_platform_validates():
    from collector.platforms.base import validate_platform
    for p in registry.PLATFORMS:
        validate_platform(p)  # raises on malformed
