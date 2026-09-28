"""Path normalization shared by the M3U reader and the rekordbox collection index.

rekordbox matches imported tracks by exact file path, but the same file can be written
many ways: different Unicode normalization (macOS stores NFD, most apps write NFC),
different letter case (APFS and NTFS are case-insensitive by default), backslashes vs
forward slashes on Windows, ``file://`` URLs, or relative paths. ``path_key`` folds all of
those into one comparison key so a playlist line always finds the track you already have.
"""

from __future__ import annotations

import os
import posixpath
import re
import unicodedata

_WIN_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def is_absolute_any(path: str) -> bool:
    """True for absolute POSIX paths, Windows drive paths (C:\\...) and UNC paths (\\\\server\\share)."""
    return path.startswith("/") or path.startswith("\\\\") or bool(_WIN_DRIVE.match(path))


def normalize(path: str) -> str:
    """Canonical display form: NFC Unicode, forward slashes, no redundant separators."""
    path = unicodedata.normalize("NFC", path.strip())
    unc = path.startswith("\\\\") or path.startswith("//")
    path = path.replace("\\", "/")
    path = posixpath.normpath(path)
    if unc and not path.startswith("//"):
        path = "/" + path  # posixpath collapses the leading // of UNC paths
    return path


def path_key(path: str, case_sensitive: bool = False) -> str:
    """Comparison key for two paths that point at the same file."""
    key = normalize(path)
    return key if case_sensitive else key.casefold()


def file_exists(path: str) -> bool:
    """Existence check that tolerates NFC/NFD differences in the file name."""
    for form in ("NFC", "NFD"):
        candidate = unicodedata.normalize(form, path)
        if os.name == "nt":
            candidate = candidate.replace("/", "\\")
        if os.path.exists(candidate):
            return True
    return False
