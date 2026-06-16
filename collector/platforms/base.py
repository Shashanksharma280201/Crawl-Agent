"""Platform/Collection contract shared by every platform module + the engine."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Collection:
    key: str                 # unique within a platform, e.g. "bookmarks", "likes"
    name: str                # UI/MD label, e.g. "Bookmarks"
    kind: str                # "bookmarks" | "likes"
    url: str                 # may contain "{username}"
    nav: str                 # "scroll" | "paginate"
    extract_js: str          # JS returning an array of {type,title,author,url,meta}
    next_js: str = ""        # paginate only: JS returning next page URL or ""
    count_js: str = ""       # scroll only: JS probe for stall detection (optional)


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    color: str
    blurb: str
    domain: str
    auth_cookie: str
    login_url: str
    collections: tuple
    needs_username: bool = False
    username_js: str = ""

    @property
    def default_collection(self):
        return self.collections[0]


def validate_platform(p):
    """Raise ValueError if the platform contract is malformed."""
    if not p.key:
        raise ValueError("platform key is empty")
    if not p.collections:
        raise ValueError(f"{p.key}: no collections declared")
    keys = [c.key for c in p.collections]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{p.key}: duplicate collection keys {keys}")
    for c in p.collections:
        if c.kind not in ("bookmarks", "likes"):
            raise ValueError(f"{p.key}.{c.key}: bad kind {c.kind!r}")
        if c.nav not in ("scroll", "paginate"):
            raise ValueError(f"{p.key}.{c.key}: bad nav {c.nav!r}")
        if c.nav == "paginate" and not c.next_js:
            raise ValueError(f"{p.key}.{c.key}: paginate needs next_js")
        if p.needs_username and "{username}" in c.url and not p.username_js:
            raise ValueError(f"{p.key}: needs_username but no username_js")
