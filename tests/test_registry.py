from collector import registry


def test_registry_loads_known_platforms():
    keys = {p.key for p in registry.PLATFORMS}
    assert {"youtube", "reddit"} <= keys


def test_by_key_lookup():
    assert registry.BY_KEY["youtube"].name == "YouTube"


def test_every_platform_validates():
    from collector.platforms.base import validate_platform
    for p in registry.PLATFORMS:
        validate_platform(p)  # raises on malformed
