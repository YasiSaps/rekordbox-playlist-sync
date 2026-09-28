"""End-to-end self test on a temporary COPY of your library. Your real library is never
opened for writing; the copy is deleted afterwards."""

from __future__ import annotations

import contextlib
import io
import os
import platform
import shutil
import tempfile
import unicodedata
from urllib.parse import quote

from . import __version__, backup, config
from .paths import file_exists, is_absolute_any


def _pick_tracks(lib, n):
    picked = []
    # prefer prepared tracks (with cues) so cue preservation is actually exercised
    for t in sorted(lib.collection(), key=lambda t: -t.cues):
        if t.path and is_absolute_any(t.path) and file_exists(t.path):
            picked.append(t)
            if len(picked) == n:
                break
    return picked


def _variant(i, path):
    if i == 0:
        return "file://" + quote(path if path.startswith("/") else "/" + path)
    if i == 1:
        return unicodedata.normalize("NFD", path)
    if i == 2:
        upper = path.upper()
        if os.path.exists(upper) or os.name == "nt":  # case-insensitive file system
            return upper
    return path


def run(db_path=None) -> int:
    from . import cli, rekordbox
    from .rekordbox import Library, default_db_path

    say = print
    say(f"rbsync {__version__} self test  ({platform.system()} {platform.release()})")
    src = db_path or default_db_path()
    if not src:
        say("FAIL: rekordbox library not found.")
        return config.EXIT_ERROR
    src_dir = os.path.dirname(os.path.abspath(src))
    version = config.rekordbox_version(src_dir)
    say(f"rekordbox {version or 'unknown'}  -  library {src}")

    tmp = tempfile.mkdtemp(prefix="rbsync-selftest-")
    old_home = os.environ.get("RBSYNC_HOME")
    os.environ["RBSYNC_HOME"] = os.path.join(tmp, "home")
    real_running = rekordbox.is_running
    try:
        import pyrekordbox.db6.database as rbdb

        real_pid = rbdb.get_rekordbox_pid
        for name in backup.DB_FILES:
            if os.path.exists(os.path.join(src_dir, name)):
                shutil.copy2(os.path.join(src_dir, name), tmp)
        db = os.path.join(tmp, "master.db")
        say(f"Working on a temporary copy: {tmp}\n")

        # The copy is private to this test, so rekordbox being open does not matter.
        rekordbox.is_running = lambda: False
        rbdb.get_rekordbox_pid = lambda *a, **k: 0

        with Library(db) as lib:
            tracks = _pick_tracks(lib, 8)
            n_coll = len(lib.collection())
        if len(tracks) < 8:
            say("SKIP: need at least 8 tracks with files present in your collection.")
            return config.EXIT_ERROR
        cues_before = {t.id: t.cues for t in tracks}
        name = "rbsync selftest"

        def write(fname, items, variants=False):
            p = os.path.join(tmp, fname)
            lines = ["#EXTM3U"] + [_variant(i, t.path) if variants else t.path for i, t in enumerate(items)]
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return p

        def step(title, argv, expect=0):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli.main(argv + ["--db", db, "--playlist", name, "--allow-untested"])
            ok = code == expect
            say(f"  [{'PASS' if ok else 'FAIL'}] {title}")
            if not ok:
                say("        " + buf.getvalue().replace("\n", "\n        "))
            return ok, buf.getvalue()

        results = []
        v1 = write("v1.m3u8", tracks[:5], variants=True)
        results.append(step("create playlist from 5 tracks (URL / NFD / case path variants)",
                            ["apply", v1, "--create"])[0])
        with Library(db) as lib:
            pl = lib.find_playlists(name=name)
            pid = str(pl[0].ID) if len(pl) == 1 else None
            results.append(pid is not None and len(pl[0].Songs) == 5)
            say(f"  [{'PASS' if results[-1] else 'FAIL'}] playlist exists with 5 tracks")

        v2 = write("v2.m3u8", tracks[:3] + tracks[5:8])
        ok, text = step("update: keep 3, remove 2, add 3", ["apply", v2])
        results.append(ok and "+ add        3" in text and "- remove     2" in text)
        with Library(db) as lib:
            pl = lib.find_playlists(name=name)
            same = len(pl) == 1 and str(pl[0].ID) == pid
            got = sorted(str(s.ContentID) for s in pl[0].Songs) if pl else []
            results.append(same and got == sorted(t.id for t in tracks[:3] + tracks[5:8]))
            say(f"  [{'PASS' if results[-1] else 'FAIL'}] same playlist ID, exactly the new 6 tracks")
            now = {t.id: t.cues for t in lib.collection() if t.id in cues_before}
            results.append(now == cues_before and len(lib.collection()) == n_coll)
            say(f"  [{'PASS' if results[-1] else 'FAIL'}] cues unchanged, no tracks added to collection")

        ok, text = step("run again: nothing to change", ["apply", v2])
        results.append(ok and "Already up to date" in text)
        v3 = write("v3.m3u8", list(reversed(tracks[:3] + tracks[5:8])))
        results.append(step("reorder to match the file", ["apply", v3, "--reorder"])[0])
        with Library(db) as lib:
            order = lambda: [str(s.ContentID) for s in  # noqa: E731
                             sorted(lib.find_playlists(name=name)[0].Songs, key=lambda s: s.TrackNo)]
            reordered = order()
        results.append(reordered == [t.id for t in reversed(tracks[:3] + tracks[5:8])])
        say(f"  [{'PASS' if results[-1] else 'FAIL'}] order matches the file")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["restore", "latest", "--yes", "--db", db])
        with Library(db) as lib:
            restored = order()
        results.append(code == 0 and restored != reordered and sorted(restored) == sorted(reordered))
        say(f"  [{'PASS' if results[-1] else 'FAIL'}] restore latest backup undoes the reorder")
        if not results[-1]:
            say("        " + buf.getvalue().replace("\n", "\n        "))

        passed = all(results)
        say("")
        say("RESULT: " + ("PASS - rbsync works with this rekordbox library."
                          if passed else "FAIL - please do not use apply on this setup."))
        say("Please share this output in an issue so the compatibility list can be updated:")
        say("  https://github.com/YasiSaps/rekordbox-playlist-sync/issues/new?template=compatibility.yml")
        return config.EXIT_OK if passed else config.EXIT_ERROR
    finally:
        rekordbox.is_running = real_running
        try:
            rbdb.get_rekordbox_pid = real_pid
        except NameError:
            pass
        if old_home is None:
            os.environ.pop("RBSYNC_HOME", None)
        else:
            os.environ["RBSYNC_HOME"] = old_home
        shutil.rmtree(tmp, ignore_errors=True)
