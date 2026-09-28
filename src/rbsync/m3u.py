"""Reader for M3U / M3U8 playlist files (as written by rekordbox, Serato, iTunes/Music,
VLC, foobar2000, Traktor exports, scripts and AI assistants)."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

from .paths import is_absolute_any, normalize

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def decode(raw: bytes) -> str:
    """UTF-16 when the file starts with its byte-order mark (some Windows tools write it),
    else UTF-8 (with or without BOM), then the Windows code page M3U files often use."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
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


def title(text: str) -> Optional[str]:
    """The playlist name from an ``#PLAYLIST:`` line (extended M3U), if there is one."""
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if line.upper().startswith("#PLAYLIST:"):
            name = line[len("#PLAYLIST:"):].strip()
            return name or None
    return None


def load(path: str) -> Tuple[Optional[str], List[str]]:
    """Read an M3U/M3U8 file from disk: (#PLAYLIST name or None, track paths)."""
    with open(path, "rb") as f:
        text = decode(f.read())
    return title(text), parse(text, os.path.dirname(os.path.abspath(path)))


def read(path: str) -> List[str]:
    """Read the track paths of an M3U/M3U8 file."""
    return load(path)[1]
