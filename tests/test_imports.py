def test_collector_package_imports():
    from collector import browser, cdp, registry, storage  # noqa: F401
    assert hasattr(browser, "ensure_headless")
    assert hasattr(cdp, "connect")
