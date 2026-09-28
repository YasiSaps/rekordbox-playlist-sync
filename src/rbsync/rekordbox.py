"""Thin adapter around pyrekordbox. The only module that touches the rekordbox database."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from .paths import path_key
from .planner import Entry, Plan, Track

PLAYLIST, FOLDER, SMART = 0, 1, 4


class RekordboxError(Exception):
    pass


def _quiet():
    logging.getLogger("pyrekordbox").setLevel(logging.ERROR)


def is_running() -> bool:
    """True while the rekordbox application is open (macOS and Windows)."""
    _quiet()
    from pyrekordbox.utils import get_rekordbox_pid

    return bool(get_rekordbox_pid())


def default_db_path() -> Optional[str]:
    _quiet()
    try:
        from pyrekordbox.config import get_config
    except Exception:  # pragma: no cover
        return None
    for version in ("rekordbox7", "rekordbox6"):
        try:
            path = (get_config(version) or {}).get("db_path")
        except Exception:
            path = None
        if path and os.path.exists(path):
            return str(path)
    return None


@dataclass
class PlaylistInfo:
    id: str
    name: str
    path: str  # "Folder / Sub / Name"
    kind: str  # playlist | folder | smart
    count: int


class Library:
    """An open rekordbox library (master.db)."""

    def __init__(self, db_path: Optional[str] = None):
        _quiet()
        try:
            from pyrekordbox import Rekordbox6Database
        except ImportError as e:  # pragma: no cover
            raise RekordboxError(f"pyrekordbox is not installed: {e}")
        self.db_path = db_path or default_db_path()
        if not self.db_path:
            raise RekordboxError(
                "Could not find your rekordbox library (master.db). Is rekordbox 6 or 7 "
                "installed and has it been opened at least once? You can pass --db PATH."
            )
        self.db_dir = os.path.dirname(os.path.abspath(self.db_path))
        try:
            self.db = Rekordbox6Database(path=self.db_path)
        except Exception as e:
            raise RekordboxError(f"Could not open {self.db_path}: {e}")

    # --- context manager -------------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass

    # --- reading ---------------------------------------------------------------------
    @staticmethod
    def _track(c) -> Track:
        return Track(
            id=str(c.ID),
            path=c.FolderPath or "",
            title=c.Title or "",
            artist=(c.Artist.Name if c.Artist else "") or "",
            cues=len(c.Cues or []),
        )

    def collection(self) -> List[Track]:
        return [self._track(c) for c in self.db.get_content().all()]

    def _path_of(self, pl) -> str:
        parts, node, guard = [pl.Name], pl, 0
        while node.Parent is not None and guard < 64:
            node = node.Parent
            parts.append(node.Name)
            guard += 1
        return " / ".join(reversed(parts))

    def playlists(self) -> List[PlaylistInfo]:
        kinds = {PLAYLIST: "playlist", FOLDER: "folder", SMART: "smart"}
        out = []
        for p in self.db.get_playlist().all():
            kind = kinds.get(p.Attribute, "other")
            count = len(p.Songs) if kind == "playlist" else 0
            out.append(PlaylistInfo(str(p.ID), p.Name, self._path_of(p), kind, count))
        return sorted(out, key=lambda x: x.path.casefold())

    def find_playlists(self, name: Optional[str] = None, playlist_id: Optional[str] = None):
        if playlist_id:
            # pyrekordbox returns a single object (or None) for an ID lookup
            found = self.db.get_playlist(ID=str(playlist_id))
            return [found] if found is not None else []
        return [p for p in self.db.get_playlist(Name=name).all() if p.Attribute == PLAYLIST]

    def find_folder(self, name: str):
        return [p for p in self.db.get_playlist(Name=name).all() if p.Attribute == FOLDER]

    def entries(self, playlist) -> List[Entry]:
        return [
            Entry(str(s.ID), s.TrackNo, self._track(s.Content) if s.Content else None)
            for s in playlist.Songs
        ]

    # --- writing ---------------------------------------------------------------------
    def apply(self, plan: Plan, reorder: bool = False, folder: Optional[str] = None,
              case_sensitive: bool = False):
        """Apply a plan. Raises if rekordbox is running (checked again by pyrekordbox)."""
        if is_running():
            raise RekordboxError("rekordbox is running. Quit rekordbox, then try again.")
        db = self.db
        if plan.create:
            parent = None
            if folder:
                found = self.find_folder(folder)
                if len(found) > 1:
                    raise RekordboxError(f"More than one folder is called '{folder}'.")
                parent = found[0] if found else db.create_playlist_folder(folder)
            playlist = db.create_playlist(plan.playlist_name, parent=parent)
        else:
            found = self.find_playlists(playlist_id=plan.playlist_id)
            if len(found) != 1 or found[0].Attribute != PLAYLIST:
                raise RekordboxError(f"Playlist {plan.playlist_id} not found.")
            playlist = found[0]

        for e in plan.remove:
            db.remove_from_playlist(playlist, e.song_id)
        for t in plan.add:
            db.add_to_playlist(playlist, t.id)

        moves = 0
        if reorder:
            db.flush()
            key = lambda p: path_key(p, case_sensitive)  # noqa: E731
            order = {key(t.path): i for i, t in enumerate(plan.desired)}
            songs = sorted(playlist.Songs, key=lambda s: s.TrackNo)
            target = sorted(songs, key=lambda s: order.get(key(s.Content.FolderPath), 10 ** 9))
            for i, s in enumerate(target, start=1):
                if s.TrackNo != i:
                    db.move_song_in_playlist(playlist, s, i)
                    moves += 1
        db.commit()
        return str(playlist.ID), moves

    def verify(self, playlist_id: str, plan: Plan, reorder: bool, case_sensitive: bool = False):
        """Re-read the playlist and confirm it matches the desired contents."""
        key = lambda p: path_key(p, case_sensitive)  # noqa: E731
        found = self.find_playlists(playlist_id=playlist_id)
        if len(found) != 1:
            return False, "playlist not found after writing"
        songs = sorted(found[0].Songs, key=lambda s: s.TrackNo)
        got = [key(s.Content.FolderPath) for s in songs if s.Content]
        want = [key(t.path) for t in plan.desired]
        if sorted(got) != sorted(want):
            return False, f"playlist has {len(got)} tracks, expected {len(want)}"
        if reorder and got != want:
            return False, "track order differs from the playlist file"
        if [s.TrackNo for s in songs] != list(range(1, len(songs) + 1)):
            return False, "track numbers are not contiguous"
        return True, f"{len(got)} tracks"
