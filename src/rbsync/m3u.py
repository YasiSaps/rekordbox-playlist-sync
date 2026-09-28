"""Reader for M3U / M3U8 playlist files (as written by rekordbox, Serato, iTunes/Music,
VLC, foobar2000, Traktor exports, scripts and AI assistants)."""

from __future__ import annotations

import os
from typing import List
from urllib.parse import unquote, urlparse

from .paths import is_absolute_any, normalize

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def decode(raw: bytes) -> str:
    """UTF-8 (with or without BOM) first, then the Windows code page M3U files often use."""
    for enc in ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")  # pragma: no cover - latin-1 never fails


def _from_url(line: str) -> str:
    parsed = urlparse(line)
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        return "//" + parsed.netloc + path  # file://server/share/x.mp3 -> UNC
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]  # file:///C:/Music/x.mp3 -> C:/Music/x.mp3
    return path


def parse(text: str, base_dir: str = "") -> List[str]:
    """Return the track paths in playlist order, normalized, comments and tags skipped."""
    tracks = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("file:"):
            line = _from_url(line)
        elif "://" in line:
            continue  # http(s) streams and other URLs are not local files
        if line.startswith("~"):
            line = os.path.expanduser(line)
        if not is_absolute_any(line) and base_dir:
            line = os.path.join(base_dir, line)
        tracks.append(normalize(line))
    return tracks


def read(path: str) -> List[str]:
    """Read an M3U/M3U8 file from disk."""
    with open(path, "rb") as f:
        raw = f.read()
    return parse(decode(raw), os.path.dirname(os.path.abspath(path)))
