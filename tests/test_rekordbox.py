"""Integration tests: rbsync against a real (unencrypted) rekordbox-schema database."""

import unicodedata

import pytest

from rbsync.planner import build_plan
from rbsync.rekordbox import FOLDER, Library, RekordboxError

import fakelib


@pytest.fixture
def db(tmp_path, monkeypatch):
    fakelib.not_running(monkeypatch)
    return fakelib.make(tmp_path)


@pytest.fixture
def paths(tmp_path):
    return lambda *ns: [fakelib.music(tmp_path, n) for n in ns]


def open_lib(db):
    return Library(db, unlock=False)


def plan_for(lib, name, desired, create=False):
    res = lib.resolve(name)
    pl = res.matches[0] if res.matches else None
    return build_plan(name, str(pl.ID) if pl else None, desired, lib.collection(),
                      lib.entries(pl) if pl else [], create=create)


def live_rows(lib, playlist_id):
    pl = lib.playlist_by_id(playlist_id)
    return [(s.ContentID, s.TrackNo) for s in lib._songs(pl)]


def test_soft_deleted_rows_are_invisible(db):
    with open_lib(db) as lib:
        assert {t.id for t in lib.collection()} == {str(n) for n in range(1, 9)}
        assert lib.track("3").cues == 1  # the deleted cue is not counted
        assert lib.track("9") is None  # deleted track
        names = [p.path for p in lib.playlists()]
        assert "Old Stuff" not in names and names.count("Warm Up") == 1
        entries = lib.entries(lib.playlist_by_id("11"))
        assert [e.song_id for e in entries] == ["s1", "s2", "s3", "s9"]  # deleted row sx hidden
        assert entries[-1].track is None  # row pointing at a deleted track
        assert lib.playlist_by_id("15") is None


def test_deleted_track_sharing_a_path_is_never_chosen(db, paths):
    with open_lib(db) as lib:
        p = plan_for(lib, "Warm Up", paths(7, 3))
        assert [t.id for t in p.add] == ["3"]
        assert not p.collection_duplicates


def test_name_resolution(db):
    with open_lib(db) as lib:
        assert lib.resolve("Warm Up").how == "exact"  # deleted twin ignored: no ambiguity
        assert [p.ID for p in lib.resolve("warm up").matches] == ["12"]
        assert lib.resolve("warm up").how == "case-insensitive"
        assert [p.ID for p in lib.resolve("Gigs / Peak Time").matches] == ["11"]
        assert [p.ID for p in lib.resolve(unicodedata.normalize("NFD", "Café Del Mar")).matches] == ["16"]
        res = lib.resolve("Techno")
        assert not res.matches and res.smart == ["Techno"]
        assert lib.resolve("Peek Time").suggestions == ["Peak Time"]
        assert lib.resolve("peek TIME").suggestions == ["Peak Time"]
        assert not lib.resolve("Old Stuff").matches  # deleted
        assert [p.ID for p in lib.resolve("Gigs", kind=FOLDER).matches] == ["10"]


def test_apply_update_compacts_track_numbers(db, paths):
    with open_lib(db) as lib:
        p = plan_for(lib, "Peak Time", paths(1, 3, 5, 6))
        assert [e.song_id for e in p.remove] == ["s2", "s9"]
        assert [t.id for t in p.add] == ["5", "6"]
        pid, _ = lib.apply(p)
    with open_lib(db) as lib:
        assert pid == "11"
        assert live_rows(lib, pid) == [("1", 1), ("3", 2), ("5", 3), ("6", 4)]
        assert lib.verify(pid, p, reorder=False) == (True, "4 tracks")
        again = plan_for(lib, "Peak Time", paths(1, 3, 5, 6))
        assert not again.changed


def test_apply_reorder(db, paths):
    with open_lib(db) as lib:
        p = plan_for(lib, "Peak Time", paths(6, 3, 1))
        pid, moves = lib.apply(p, reorder=True)
    with open_lib(db) as lib:
        assert live_rows(lib, pid) == [("6", 1), ("3", 2), ("1", 3)]
        assert moves == 3
        assert lib.verify(pid, p, reorder=True)[0]


def test_create_in_nested_folder(db, paths):
    with open_lib(db) as lib:
        name = unicodedata.normalize("NFD", "Día Set")
        p = plan_for(lib, name, paths(2, 4), create=True)
        assert p.create
        pid, _ = lib.apply(p, folder="Gigs / 2026")
    with open_lib(db) as lib:
        pl = lib.playlist_by_id(pid)
        assert pl.Name == "Día Set"  # stored NFC, like rekordbox's own UI
        assert lib._path_of(pl) == "Gigs / 2026 / Día Set"
        assert live_rows(lib, pid) == [("2", 1), ("4", 2)]
        assert len(lib.resolve("Gigs", kind=FOLDER).matches) == 1  # existing folder reused


def test_apply_refuses_when_rekordbox_runs(db, paths, monkeypatch):
    from rbsync import rekordbox

    with open_lib(db) as lib:
        p = plan_for(lib, "Warm Up", paths(1))
        monkeypatch.setattr(rekordbox, "is_running", lambda: True)
        with pytest.raises(RekordboxError):
            lib.apply(p)
