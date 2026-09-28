"""Thin adapter around pyrekordbox. The only module that touches the rekordbox database.

rekordbox 6/7 often *soft-deletes* rows: deleted tracks, playlists and playlist entries stay in
the database with ``rb_local_deleted = 1`` (for Cloud Library Sync). pyrekordbox returns those
rows like any other, so every query here filters them out explicitly.
"""

from __future__ import annotations

import datetime
import difflib
import logging
import os
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .paths import path_key
from .planner import Entry, Plan, Track

PLAYLIST, FOLDER, SMART = 0, 1, 4
KINDS = {PLAYLIST: "playlist", FOLDER: "folder", SMART: "smart"}


class RekordboxError(Exception):
    pass


def _quiet():
    logging.getLogger("pyrekordbox").setLevel(logging.ERROR)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "").strip())


def _live(column):
    """SQL condition: the row has not been soft-deleted."""
    from sqlalchemy import or_

    return or_(column == 0, column.is_(None))


def _is_live(row) -> bool:
    return not getattr(row, "rb_local_deleted", 0)


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


@dataclass
class Resolution:
    """Result of looking up a playlist by name."""

    matches: list = field(default_factory=list)  # live regular playlists
    how: str = ""  # exact | path | case-insensitive
    smart: List[str] = field(default_factory=list)  # intelligent playlists with that name
    suggestions: List[str] = field(default_factory=list)


class Library:
    """An open rekordbox library (master.db)."""

    def __init__(self, db_path: Optional[str] = None, unlock: bool = True):
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
            self.db = Rekordbox6Database(path=self.db_path, unlock=unlock)
        except Exception as e:
            raise RekordboxError(f"Could not open {self.db_path}: {e}")
        self._collection: Optional[List[Track]] = None
        self._by_id: Dict[str, Track] = {}

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
    def collection(self) -> List[Track]:
        """All live tracks, loaded with two bulk queries (fast on 50k+ track libraries)."""
        if self._collection is None:
            from pyrekordbox.db6 import tables as T
            from sqlalchemy import func

            cues = dict(
                self.db.query(T.DjmdCue.ContentID, func.count(T.DjmdCue.ID))
                .filter(_live(T.DjmdCue.rb_local_deleted))
                .group_by(T.DjmdCue.ContentID)
                .all()
            )
            rows = (
                self.db.query(T.DjmdContent.ID, T.DjmdContent.FolderPath,
                              T.DjmdContent.Title, T.DjmdArtist.Name)
                .outerjoin(T.DjmdArtist, T.DjmdArtist.ID == T.DjmdContent.ArtistID)
                .filter(_live(T.DjmdContent.rb_local_deleted))
                .all()
            )
            self._collection = [
                Track(str(i), fp or "", title or "", artist or "", int(cues.get(i, 0)))
                for i, fp, title, artist in rows
            ]
            self._by_id = {t.id: t for t in self._collection}
        return self._collection

    def track(self, content_id: str) -> Optional[Track]:
        self.collection()
        return self._by_id.get(str(content_id))

    def _live_playlists(self):
        from pyrekordbox.db6 import tables as T

        return self.db.query(T.DjmdPlaylist).filter(_live(T.DjmdPlaylist.rb_local_deleted)).all()

    def _path_of(self, pl) -> str:
        parts, node, guard = [pl.Name], pl, 0
        while node.Parent is not None and guard < 64:
            node = node.Parent
            parts.append(node.Name)
            guard += 1
        return " / ".join(reversed(parts))

    def _songs(self, playlist) -> list:
        """Live playlist rows, in playlist order."""
        return sorted((s for s in playlist.Songs if _is_live(s)), key=lambda s: s.TrackNo or 0)

    def playlists(self) -> List[PlaylistInfo]:
        out = []
        for p in self._live_playlists():
            kind = KINDS.get(p.Attribute, "other")
            count = len(self._songs(p)) if kind == "playlist" else 0
            out.append(PlaylistInfo(str(p.ID), p.Name, self._path_of(p), kind, count))
        return sorted(out, key=lambda x: x.path.casefold())

    def playlist_by_id(self, playlist_id: str):
        found = self.db.get_playlist(ID=str(playlist_id))  # single object or None
        if found is None or not _is_live(found):
            return None
        return found

    def resolve(self, name: str, kind: int = PLAYLIST) -> Resolution:
        """Find live playlists (or folders) by name. Accepts "Folder / Name" paths, and
        tolerates Unicode normalization and letter-case differences."""
        want = _nfc(name)
        split = lambda s: [p.strip() for p in s.replace("\\", "/").split("/") if p.strip()]  # noqa: E731
        want_path = [p.casefold() for p in split(want)]
        live = self._live_playlists()
        same_kind = [p for p in live if p.Attribute == kind]
        res = Resolution()

        res.matches = [p for p in same_kind if _nfc(p.Name) == want]
        res.how = "exact"
        if not res.matches and len(want_path) > 1:
            res.matches = [p for p in same_kind
                           if [x.casefold() for x in split(_nfc(self._path_of(p)))] == want_path]
            res.how = "path"
        if not res.matches:
            res.matches = [p for p in same_kind if _nfc(p.Name).casefold() == want.casefold()]
            res.how = "case-insensitive"
        if not res.matches:
            res.how = ""
            if kind == PLAYLIST:
                res.smart = [self._path_of(p) for p in live
                             if p.Attribute == SMART and _nfc(p.Name).casefold() == want.casefold()]
            names = {_nfc(p.Name).casefold(): _nfc(p.Name) for p in same_kind}
            close = difflib.get_close_matches(want.casefold(), sorted(names), n=3, cutoff=0.6)
            res.suggestions = [names[c] for c in close]
        return res

    def entries(self, playlist) -> List[Entry]:
        """Live rows of a playlist. Rows pointing at deleted/missing tracks get track=None
        (the planner removes them)."""
        return [Entry(str(s.ID), s.TrackNo or 0, self.track(s.ContentID))
                for s in self._songs(playlist)]

    # --- writing ---------------------------------------------------------------------
    def apply(self, plan: Plan, reorder: bool = False, folder: Optional[str] = None,
              case_sensitive: bool = False):
        """Apply a plan. Raises if rekordbox is running (checked again by pyrekordbox)."""
        if is_running():
            raise RekordboxError("rekordbox is running. Quit rekordbox, then try again.")
        db = self.db
        if plan.create:
            parent = self._folder(folder) if folder else None
            playlist = db.create_playlist(_nfc(plan.playlist_name), parent=parent)
        else:
            playlist = self.playlist_by_id(plan.playlist_id)
            if playlist is None or playlist.Attribute != PLAYLIST:
                raise RekordboxError(f"Playlist {plan.playlist_id} not found.")

        for e in plan.remove:
            db.remove_from_playlist(playlist, e.song_id)
        for t in plan.add:
            db.add_to_playlist(playlist, t.id)
        db.flush()

        # Final order: current order (new tracks appended), or the file's order with
        # --reorder. Track numbers are rewritten to 1..n over *live* rows only, because
        # pyrekordbox counts soft-deleted rows when numbering and can leave gaps.
        songs = self._songs(playlist)
        if reorder:
            key = lambda p: path_key(p, case_sensitive)  # noqa: E731
            order = {key(t.path): i for i, t in enumerate(plan.desired)}
            pos = lambda s: order.get(key(s.Content.FolderPath) if s.Content else "", 10 ** 9)  # noqa: E731
            songs = sorted(songs, key=pos)
        now = datetime.datetime.now()
        moves = 0
        for i, s in enumerate(songs, start=1):
            if s.TrackNo != i:
                s.TrackNo = i
                s.updated_at = now
                moves += 1
        if moves:
            playlist.updated_at = now
        db.commit()
        return str(playlist.ID), moves

    def _folder(self, folder: str):
        """Find a folder by name or "A / B" path; create any missing levels of a path."""
        found = self.resolve(folder, kind=FOLDER).matches
        if len(found) > 1:
            raise RekordboxError(f"More than one folder is called '{folder}'. Use its full "
                                 "path, e.g. --folder \"Gigs / 2026\".")
        if found:
            return found[0]
        parts = [_nfc(p) for p in folder.replace("\\", "/").split("/") if p.strip()]
        parent = None
        for part in parts:
            children = [p for p in self._live_playlists() if p.Attribute == FOLDER
                        and _nfc(p.Name) == part
                        and (p.Parent is None if parent is None else p.ParentID == parent.ID)]
            parent = children[0] if children else self.db.create_playlist_folder(part, parent=parent)
        return parent

    def verify(self, playlist_id: str, plan: Plan, reorder: bool, case_sensitive: bool = False):
        """Re-read the playlist and confirm it matches the desired contents."""
        key = lambda p: path_key(p, case_sensitive)  # noqa: E731
        playlist = self.playlist_by_id(playlist_id)
        if playlist is None:
            return False, "playlist not found after writing"
        songs = self._songs(playlist)
        tracks = [self.track(s.ContentID) for s in songs]
        if any(t is None for t in tracks):
            return False, "playlist contains a deleted or unknown track"
        got = [key(t.path) for t in tracks]
        want = [key(t.path) for t in plan.desired]
        if sorted(got) != sorted(want):
            return False, f"playlist has {len(got)} tracks, expected {len(want)}"
        if reorder and got != want:
            return False, "track order differs from the playlist file"
        if [s.TrackNo for s in songs] != list(range(1, len(songs) + 1)):
            return False, "track numbers are not contiguous"
        return True, f"{len(got)} tracks"
