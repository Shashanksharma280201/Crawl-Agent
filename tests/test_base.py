import pytest

from collector.platforms.base import Collection, Platform, validate_platform


def _collection(key="saved", kind="bookmarks", nav="scroll", next_js=""):
    return Collection(key=key, name=key.title(), kind=kind, url="https://e.com/s",
                      nav=nav, extract_js="[]", next_js=next_js)


def _platform(collections):
    return Platform(key="e", name="E", color="#000", blurb="b", domain="e.com",
                    auth_cookie="c", login_url="https://e.com/login",
                    collections=tuple(collections))


def test_default_collection_is_first():
    p = _platform([_collection("a"), _collection("b")])
    assert p.default_collection.key == "a"


def test_validate_rejects_duplicate_collection_keys():
    p = _platform([_collection("x"), _collection("x")])
    with pytest.raises(ValueError):
        validate_platform(p)


def test_validate_rejects_empty_collections():
    p = _platform([])
    with pytest.raises(ValueError):
        validate_platform(p)


def test_validate_requires_next_js_for_paginate():
    p = _platform([_collection(nav="paginate", next_js="")])
    with pytest.raises(ValueError):
        validate_platform(p)


def test_validate_accepts_valid_platform():
    p = _platform([_collection(), _collection("liked", kind="likes")])
    validate_platform(p)  # should not raise
