"""Which files of a profile's browser data make up each part a clone can take.

The two engines keep the same things in different places: Camoufox in a
Firefox profile directory, Chrome in a Chromium user data directory ("Default"
holds the profile; "Local State" holds the key that encrypts its cookies and
passwords, so it travels with either). Patterns are relative to the profile's
data directory and may end in "*" to take SQLite's -wal / -shm / -journal files.
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Collection

# A clone always gets a new identity and never takes locks, caches or a draft.
SKIP = {
    "fingerprint.json",
    "chrome_persona.json",
    "recording.json",
    "parent.lock",
    "lock",
    ".parentlock",
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
    "cache2",
    "startupCache",
    "Cache",
    "Code Cache",
    "GPUCache",
    "ShaderCache",
    "GrShaderCache",
}

# Browser data parts, in the order the interfaces list them.
PARTS = ("cookies", "history", "site_data", "passwords", "tabs")

_CAMOUFOX: dict[str, tuple[str, ...]] = {
    "cookies": ("cookies.sqlite*",),
    "history": ("places.sqlite*", "favicons.sqlite*", "formhistory.sqlite*", "bookmarkbackups"),
    "site_data": (
        "storage",
        "storage.sqlite*",
        "webappsstore.sqlite*",
        "permissions.sqlite*",
        "content-prefs.sqlite*",
    ),
    "passwords": ("logins.json", "logins.db*", "logins-backup.json", "key4.db", "cert9.db"),
    "tabs": ("tabs.json",),
}
_CHROME: dict[str, tuple[str, ...]] = {
    "cookies": ("Local State", "Default/Cookies*", "Default/Network/Cookies*"),
    "history": (
        "Default/History*",
        "Default/Favicons*",
        "Default/Bookmarks*",
        "Default/Top Sites*",
        "Default/Visited Links",
        "Default/Web Data*",
    ),
    "site_data": (
        "Default/Local Storage",
        "Default/Session Storage",
        "Default/IndexedDB",
        "Default/databases",
        "Default/Storage",
        "Default/File System",
    ),
    "passwords": ("Local State", "Default/Login Data*"),
    "tabs": ("tabs.json",),
}


def patterns(engine: str, parts: Collection[str]) -> list[str]:
    table = _CHROME if engine == "chrome" else _CAMOUFOX
    out: list[str] = []
    for part in PARTS:
        if part in parts:
            out.extend(p for p in table[part] if p not in out)
    return out


def _ignore(_dir: str, names: list[str]) -> list[str]:
    return [n for n in names if n in SKIP]


def copy_parts(src: pathlib.Path, dst: pathlib.Path, engine: str, parts: Collection[str]) -> int:
    """Copy the chosen parts from one data directory to another; returns the files copied."""
    copied = 0
    for pattern in patterns(engine, parts):
        for path in sorted(src.glob(pattern)):
            if path.name in SKIP:
                continue
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.is_dir():
                shutil.copytree(path, target, ignore=_ignore, dirs_exist_ok=True)
                copied += sum(1 for p in target.rglob("*") if p.is_file())
            elif path.is_file():
                shutil.copy2(path, target)
                copied += 1
    return copied
