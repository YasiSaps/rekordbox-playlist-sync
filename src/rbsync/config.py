"""Locations, versions and constants."""

from __future__ import annotations

import os
import re
from typing import Optional

# rekordbox versions (major.minor) that rbsync has been verified against end-to-end,
# including a USB sync. Writing to other versions requires --allow-untested.
TESTED_VERSIONS = ("7.2",)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2  # rekordbox running, ambiguous playlist name, user cancelled
EXIT_UNTESTED = 3  # rekordbox version not verified


def home() -> str:
    """Where backups and the change log live. Override with the RBSYNC_HOME variable."""
    env = os.environ.get("RBSYNC_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.expanduser("~"), "Documents", "rbsync")


DEFAULT_KEEP_BACKUPS = 30
LOG_MAX_BYTES = 2 * 1024 * 1024


def keep_backups() -> int:
    """How many backups to keep (RBSYNC_KEEP_BACKUPS, default 30; 0 keeps all)."""
    try:
        return max(0, int(os.environ.get("RBSYNC_KEEP_BACKUPS", DEFAULT_KEEP_BACKUPS)))
    except ValueError:
        return DEFAULT_KEEP_BACKUPS


def backups_dir() -> str:
    return os.path.join(home(), "backups")


def log_path() -> str:
    return os.path.join(home(), "rbsync.log")


def rekordbox_version(db_dir: str) -> Optional[str]:
    """Read the rekordbox version that last wrote the library (masterPlaylists6.xml)."""
    xml = os.path.join(db_dir, "masterPlaylists6.xml")
    try:
        with open(xml, encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return None
    m = re.search(r'<PRODUCT[^>]*Version="([^"]+)"', head)
    return m.group(1) if m else None


def is_tested(version: Optional[str]) -> bool:
    if not version:
        return False
    return any(version == v or version.startswith(v + ".") for v in TESTED_VERSIONS)
