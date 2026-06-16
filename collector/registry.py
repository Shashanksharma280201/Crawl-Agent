"""Discovers and validates all platform modules. Add a module name here (and
create collector/platforms/<name>.py with a PLATFORM) to register a platform."""
import importlib

from collector.platforms.base import validate_platform

# Plan B appends: twitter, pinterest, linkedin, instagram, tiktok, facebook
_MODULE_NAMES = ["youtube", "reddit"]


def load_platforms():
    plats = []
    for name in _MODULE_NAMES:
        mod = importlib.import_module(f"collector.platforms.{name}")
        validate_platform(mod.PLATFORM)
        plats.append(mod.PLATFORM)
    return plats


PLATFORMS = load_platforms()
BY_KEY = {p.key: p for p in PLATFORMS}


def label_map(platform):
    """{collection_key: human label} for one platform — used by storage + web."""
    return {c.key: c.name for c in platform.collections}
