"""The command line against a real (unencrypted) rekordbox-schema library."""

import json
import os

import pytest

from rbsync import backup, cli, config, lock
from rbsync.rekordbox import Library

import fakelib


@pytest.fixture
def lib_db(tmp_path, monkeypatch):
    fakelib.not_running(monkeypatch)
    monkeypatch.setenv("RBSYNC_HOME", str(tmp_path / "home"))
    db = fakelib.make(tmp_path)
    monkeypatch.setattr(cli, "_open_library", lambda args: Library(db, unlock=False))
    return db


@pytest.fixture
def m3u(tmp_path):
    def write(name, *tracks, title=None, extra=()):
        f = tmp_path / name
        lines = ["#EXTM3U"] + ([f"#PLAYLIST:{title}"] if title else [])
        lines += [fakelib.music(tmp_path, n) for n in tracks] + list(extra)
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(f)
    return write


def run(capsys, *argv):
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def test_apply_then_up_to_date(lib_db, m3u, capsys):
    f = m3u("Warm Up.m3u8", 7, 1, 2)
    code, out = run(capsys, "apply", f)
    assert code == config.EXIT_OK and "DONE." in out and "+2 / -0" in out
    code, out = run(capsys, "apply", f)
    assert code == config.EXIT_OK and "Already up to date" in out
    assert len(backup.list_backups()) == 1


def test_playlist_directive_names_the_playlist(lib_db, m3u, capsys):
    f = m3u("export-2026.m3u8", 1, 3, title="Gigs / Peak Time")
    code, out = run(capsys, "plan", f)
    assert code == config.EXIT_OK and "(ID 11" in out


def test_strict_refuses_skipped_lines(lib_db, m3u, capsys, tmp_path):
    f = m3u("Warm Up.m3u8", 7, 1, extra=[str(tmp_path / "Music" / "not-imported.mp3")])
    code, out = run(capsys, "apply", f, "--strict")
    assert code == config.EXIT_BLOCKED and "--strict" in out
    code, out = run(capsys, "apply", f)
    assert code == config.EXIT_OK and "SUMMARY: 1 line(s)" in out


def test_smart_playlist_and_suggestions(lib_db, m3u, capsys):
    code, out = run(capsys, "plan", m3u("Techno.m3u8", 1))
    assert code == config.EXIT_BLOCKED and "intelligent playlist" in out
    code, out = run(capsys, "plan", m3u("Peek Time.m3u8", 1))
    assert code == config.EXIT_BLOCKED and 'Did you mean: "Peak Time"' in out


def test_json_plan(lib_db, m3u, capsys):
    code, out = run(capsys, "plan", m3u("Warm Up.m3u8", 7, 4), "--json")
    data = json.loads(out)
    assert code == 0 and data["playlist"]["id"] == "12" and [t["id"] for t in data["add"]] == ["4"]


def test_second_process_is_blocked_by_lock(lib_db, m3u, capsys, monkeypatch):
    os.makedirs(config.home(), exist_ok=True)
    with open(lock._path(), "w") as fh:
        fh.write("424242")
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: True)
    code, out = run(capsys, "apply", m3u("Warm Up.m3u8", 7, 1))
    assert code == config.EXIT_BLOCKED and "another rbsync" in out


def test_create_with_folder(lib_db, m3u, capsys):
    code, out = run(capsys, "apply", m3u("New Set.m3u8", 5, 6), "--create", "--folder", "Gigs / 2026")
    assert code == config.EXIT_OK, out
    code, out = run(capsys, "plan", m3u("x.m3u8", 5, 6), "--playlist", "Gigs / 2026 / New Set")
    assert code == config.EXIT_OK and "+ add        0" in out
