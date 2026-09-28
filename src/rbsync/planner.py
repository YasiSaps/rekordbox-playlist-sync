"""Pure diff logic: desired playlist (from a file) vs. current playlist (in rekordbox).

Nothing in this module touches rekordbox or the disk (except the injectable ``exists``
check), which keeps the core behaviour fully unit-testable on every platform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .paths import file_exists, is_absolute_any, path_key


@dataclass
class Track:
    """A track in the rekordbox collection (djmdContent)."""

    id: str
    path: str
    title: str = ""
    artist: str = ""
    cues: int = 0

    @property
    def label(self) -> str:
        name = f"{self.artist} - {self.title}" if self.artist else (self.title or self.path)
        return name


@dataclass
class Entry:
    """A row of the playlist (djmdSongPlaylist)."""

    song_id: str
    track_no: int
    track: Optional[Track]


@dataclass
class Plan:
    playlist_name: str
    playlist_id: Optional[str]
    create: bool
    desired: List[Track] = field(default_factory=list)
    add: List[Track] = field(default_factory=list)
    remove: List[Entry] = field(default_factory=list)
    keep: List[Entry] = field(default_factory=list)
    not_in_collection: List[str] = field(default_factory=list)
    missing_files: List[str] = field(default_factory=list)
    duplicate_lines: List[str] = field(default_factory=list)
    offline: List[Track] = field(default_factory=list)  # in the collection, file missing on disk
    collection_duplicates: List[Tuple[Track, List[Track]]] = field(default_factory=list)
    reorder_needed: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.create or self.add or self.remove)

    @property
    def skipped(self) -> int:
        """Lines of the playlist file that could not be used."""
        return len(self.not_in_collection) + len(self.missing_files)

    def to_dict(self) -> dict:
        t = lambda x: {"id": x.id, "path": x.path, "title": x.title, "artist": x.artist}  # noqa: E731
        e = lambda x: t(x.track) if x.track else {"id": None, "song_id": x.song_id}  # noqa: E731
        return {
            "playlist": {"name": self.playlist_name, "id": self.playlist_id, "create": self.create},
            "add": [t(x) for x in self.add],
            "remove": [e(x) for x in self.remove],
            "unchanged": len(self.keep),
            "not_in_collection": self.not_in_collection,
            "missing_files": self.missing_files,
            "duplicate_lines": self.duplicate_lines,
            "offline": [t(x) for x in self.offline],
            "collection_duplicates": [
                {"used": t(u), "others": [t(o) for o in others]}
                for u, others in self.collection_duplicates
            ],
            "reorder_needed": self.reorder_needed,
            "changed": self.changed,
        }


def index_collection(
    tracks: Iterable[Track], case_sensitive: bool = False
) -> Tuple[Dict[str, Track], Dict[str, List[Track]]]:
    """Map path key -> track. If a file is in the collection more than once (a classic
    side effect of re-importing with a differently spelled path), prefer the copy with the
    most cues, i.e. the one you actually prepared."""
    best: Dict[str, Track] = {}
    groups: Dict[str, List[Track]] = {}
    for tr in tracks:
        if not tr.path or not is_absolute_any(tr.path):
            continue  # streaming / Apple Music entries such as "apple-music:tracks:123"
        k = path_key(tr.path, case_sensitive)
        groups.setdefault(k, []).append(tr)
        if k not in best or tr.cues > best[k].cues:
            best[k] = tr
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    return best, dupes


def build_plan(
    playlist_name: str,
    playlist_id: Optional[str],
    desired_paths: List[str],
    collection: Iterable[Track],
    current: List[Entry],
    create: bool = False,
    case_sensitive: bool = False,
    exists: Callable[[str], bool] = file_exists,
) -> Plan:
    plan = Plan(playlist_name, playlist_id, create=create and playlist_id is None)
    index, dupes = index_collection(collection, case_sensitive)
    key = lambda p: path_key(p, case_sensitive)  # noqa: E731

    seen = set()
    for p in desired_paths:
        k = key(p)
        if k in seen:
            plan.duplicate_lines.append(p)
            continue
        seen.add(k)
        if k in index:
            plan.desired.append(index[k])
            if not exists(index[k].path):
                plan.offline.append(index[k])  # rekordbox will show it as missing
            if k in dupes:
                plan.collection_duplicates.append(
                    (index[k], [t for t in dupes[k] if t is not index[k]])
                )
        elif exists(p):
            plan.not_in_collection.append(p)
        else:
            plan.missing_files.append(p)

    wanted = {key(t.path) for t in plan.desired}
    present = set()
    for entry in sorted(current, key=lambda e: e.track_no):
        k = key(entry.track.path) if entry.track and entry.track.path else None
        if k is None or k not in wanted or k in present:
            plan.remove.append(entry)  # no longer wanted, orphaned, or duplicated in playlist
        else:
            present.add(k)
            plan.keep.append(entry)
    plan.add = [t for t in plan.desired if key(t.path) not in present]

    final_order = [key(e.track.path) for e in plan.keep] + [key(t.path) for t in plan.add]
    plan.reorder_needed = final_order != [key(t.path) for t in plan.desired]
    return plan
