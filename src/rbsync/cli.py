"""rbsync command line interface."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import sys
from typing import List, Optional

from . import __version__, backup, config, m3u
from .lock import Lock, LockedError
from .config import EXIT_BLOCKED, EXIT_ERROR, EXIT_OK, EXIT_UNTESTED
from .planner import Plan, build_plan

DESCRIPTION = """\
rbsync updates an existing rekordbox playlist in place from an M3U/M3U8 file.

Only the tracks that changed are added or removed, the playlist keeps its identity, and
your cues, beatgrids and analysis stay untouched. Because nothing is deleted and
re-imported, rekordbox Sync Manager / USB export only transfers what actually changed.
"""

EPILOG = """\
examples:
  rbsync plan  "Peak Time.m3u8"              show what would change (safe any time)
  rbsync apply "Peak Time.m3u8"              write the changes (quit rekordbox first)
  rbsync sync  "Peak Time.m3u8"              show changes, ask, wait for rekordbox to close, apply
  rbsync apply "Warm Up.m3u8" --create --folder "Gigs"
  rbsync restore latest                      undo the last change

docs: https://github.com/YasiSaps/rekordbox-playlist-sync
"""


class Output:
    """Prints to the console and keeps a copy for the change log."""

    def __init__(self, quiet: bool = False):
        self.lines: List[str] = []
        self.quiet = quiet
        self.code = EXIT_OK

    def __call__(self, msg: str = ""):
        self.lines.append(msg)
        if not self.quiet:
            print(msg)

    def write_log(self):
        try:
            os.makedirs(config.home(), exist_ok=True)
            log = config.log_path()
            if os.path.exists(log) and os.path.getsize(log) > config.LOG_MAX_BYTES:
                os.replace(log, log + ".1")  # keep one previous log
            with open(log, "a", encoding="utf-8") as f:
                f.write("\n".join(self.lines) + "\n\n")
        except OSError as e:
            print(f"(could not write log: {e})", file=sys.stderr)


# --- helpers ----------------------------------------------------------------------------

def _open_library(args):
    from .rekordbox import Library

    return Library(args.db)


def _name_candidates(args, file_title: Optional[str]) -> List[str]:
    """Playlist names to try, in order: --playlist, the file's #PLAYLIST line, the file name."""
    if args.playlist:
        return [args.playlist]
    stem = os.path.splitext(os.path.basename(args.file))[0]
    return [n for n in dict.fromkeys([file_title, stem]) if n]


def _make_plan(lib, args, out) -> Optional[Plan]:
    """Build the plan, or print why not and return None (with out.code set)."""
    if not os.path.isfile(args.file):
        out(f"ERROR: playlist file not found: {args.file}")
        out.code = EXIT_ERROR
        return None
    file_title, desired = m3u.load(args.file)

    if args.playlist_id:
        pl = lib.playlist_by_id(args.playlist_id)
        if pl is None or pl.Attribute != 0:
            out(f"ERROR: no regular playlist with ID {args.playlist_id}. "
                "Run 'rbsync playlists' to see IDs.")
            out.code = EXIT_ERROR
            return None
        name, found = pl.Name, [pl]
    else:
        names = _name_candidates(args, file_title)
        name, res = names[0], None
        for candidate in names:
            res = lib.resolve(candidate)
            if res.matches:
                name = candidate
                break
        found = res.matches
        if len(found) > 1:
            out(f'BLOCKED: {len(found)} playlists are called "{name}". Choose one with --playlist-id:')
            for p in found:
                out(f"    --playlist-id {p.ID}    {lib._path_of(p)}  ({len(lib.entries(p))} tracks)")
            out.code = EXIT_BLOCKED
            return None
        if found and res.how != "exact":
            out(f'Note: using playlist "{lib._path_of(found[0])}" for "{name}" ({res.how} match).')
        if not found and not args.create:
            if res.smart:
                out(f'BLOCKED: "{name}" is an intelligent playlist ({res.smart[0]}). rekordbox fills '
                    "those automatically, so rbsync cannot edit them.")
            else:
                out(f'BLOCKED: there is no playlist called "{name}" in rekordbox.')
                if res.suggestions:
                    out("  Did you mean: " + ", ".join(f'"{x}"' for x in res.suggestions) + "?")
                out("  The name comes from --playlist, the file's #PLAYLIST line, or the file name.")
                out("  Add --create to create it. Run 'rbsync playlists' to list your playlists.")
            out.code = EXIT_BLOCKED
            return None
        if found:
            name = found[0].Name

    if args.folder and found:
        out(f'Note: --folder is ignored because "{name}" already exists (it is not moved).')
    pl = found[0] if found else None
    return build_plan(
        playlist_name=name,
        playlist_id=str(pl.ID) if pl else None,
        desired_paths=desired,
        collection=lib.collection(),
        current=lib.entries(pl) if pl else [],
        create=args.create,
        case_sensitive=args.case_sensitive,
    )


def _version_gate(lib, args, out) -> bool:
    version = config.rekordbox_version(lib.db_dir)
    if config.is_tested(version) or args.allow_untested:
        return True
    out(f"BLOCKED: rekordbox {version or '(unknown version)'} has not been verified with rbsync "
        f"{__version__} (verified: {', '.join(config.TESTED_VERSIONS)}.x).")
    out("  'rbsync plan' works on any version. To write anyway, add --allow-untested "
        "(a backup is still made first).")
    out("  Please report the result: https://github.com/YasiSaps/rekordbox-playlist-sync/issues")
    out.code = EXIT_UNTESTED
    return False


def _wait_for_rekordbox_to_close(out) -> bool:
    from .rekordbox import is_running

    while is_running():
        try:
            input("rekordbox is open. Quit rekordbox (Cmd+Q / Alt+F4), then press Enter "
                  "(Ctrl+C to cancel)... ")
        except (EOFError, KeyboardInterrupt):
            out("\nCancelled. Nothing was changed.")
            return False
    return True


def _confirm(question: str) -> bool:
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _signature(plan: Plan):
    return (sorted(t.id for t in plan.add), sorted(e.song_id for e in plan.remove), plan.create)


def _header(out, action, args):
    out(f"=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  rbsync {__version__}  {action}  "
        f'"{os.path.basename(args.file)}"')


# --- commands ---------------------------------------------------------------------------

def cmd_plan(args) -> int:
    from .report import render
    from .rekordbox import RekordboxError

    out = Output(quiet=args.json)
    _header(out, "PLAN (dry run)", args)
    try:
        with _open_library(args) as lib:
            plan = _make_plan(lib, args, out)
    except RekordboxError as e:
        out(f"ERROR: {e}")
        return EXIT_ERROR
    if plan is None:
        if args.json:
            message = " ".join(line.strip() for line in out.lines[1:])
            print(json.dumps({"error": message, "exit_code": out.code}, ensure_ascii=False))
        return out.code
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
        return EXIT_OK
    for line in render(plan, args.reorder):
        out(line)
    out("")
    out("Dry run - nothing was changed. Run 'rbsync apply' (with rekordbox closed) to write.")
    return EXIT_OK


def _apply(args, interactive: bool) -> int:
    from .rekordbox import RekordboxError, is_running
    from .report import render

    out = Output()
    _header(out, "SYNC" if interactive else "APPLY", args)
    try:
        if not interactive and is_running():
            out("BLOCKED: rekordbox is running. Quit rekordbox completely, then run again.")
            return EXIT_BLOCKED

        with _open_library(args) as lib:
            plan = _make_plan(lib, args, out)
            if plan is None:
                return out.code
            for line in render(plan, args.reorder):
                out(line)
            out("")
            if args.strict and plan.skipped:
                out(f"BLOCKED (--strict): {plan.skipped} line(s) of the playlist file were skipped. "
                    "Nothing was changed.")
                return EXIT_BLOCKED
            if not plan.changed and not (args.reorder and plan.reorder_needed):
                out("Already up to date. Nothing to change.")
                return EXIT_OK
            if not _version_gate(lib, args, out):
                return out.code
        if interactive:
            if not _confirm("Apply these changes to rekordbox?"):
                out("Cancelled. Nothing was changed.")
                return EXIT_BLOCKED
            if not _wait_for_rekordbox_to_close(out):
                return EXIT_BLOCKED

        with Lock(), _open_library(args) as lib:
            fresh = _make_plan(lib, args, out)  # the library may have changed meanwhile
            if fresh is None:
                return out.code
            if _signature(fresh) != _signature(plan):
                out("The rekordbox playlist changed since the preview. Updated changes:")
                for line in render(fresh, args.reorder):
                    out(line)
                if not interactive or not _confirm("Apply these changes to rekordbox?"):
                    out("Stopped. Nothing was changed.")
                    return EXIT_BLOCKED
            plan = fresh
            version = config.rekordbox_version(lib.db_dir)
            saved = backup.create(lib.db_dir, f'before updating "{plan.playlist_name}"', version)
            out(f"Backup: {saved}")
            playlist_id, moves = lib.apply(plan, args.reorder, args.folder, args.case_sensitive)
        backup.prune(config.keep_backups())
        with _open_library(args) as lib:
            ok, detail = lib.verify(playlist_id, plan, args.reorder, args.case_sensitive)
        if args.reorder:
            out(f"Reordered: {moves} track(s) moved")
        if ok:
            out(f'DONE. "{plan.playlist_name}" (ID {playlist_id}) now has {detail}. '
                f"+{len(plan.add)} / -{len(plan.remove)}.")
            out("Open rekordbox and sync your USB as usual - only the changed tracks transfer.")
            return EXIT_OK
        out(f"WARNING: verification failed: {detail}.")
        out("  Undo with:  rbsync restore latest   (with rekordbox closed)")
        return EXIT_ERROR
    except LockedError as e:
        out(f"BLOCKED: {e}")
        return EXIT_BLOCKED
    except RekordboxError as e:
        out(f"ERROR: {e}")
        return EXIT_ERROR
    except Exception as e:  # unexpected: make sure the user knows how to undo
        out(f"ERROR: {type(e).__name__}: {e}")
        out("  If a backup was written above, undo with:  rbsync restore latest")
        return EXIT_ERROR
    finally:
        out.write_log()
        if getattr(args, "pause", False):
            try:
                input("\nPress Enter to close this window.")
            except (EOFError, KeyboardInterrupt):
                pass


def cmd_apply(args) -> int:
    return _apply(args, interactive=False)


def cmd_sync(args) -> int:
    return _apply(args, interactive=True)


def cmd_playlists(args) -> int:
    from .rekordbox import RekordboxError

    try:
        with _open_library(args) as lib:
            items = lib.playlists()
    except RekordboxError as e:
        print(f"ERROR: {e}")
        return EXIT_ERROR
    icon = {"playlist": " ", "folder": "/", "smart": "*"}
    print(f"{'ID':>12}  {'tracks':>6}  playlist   (/ = folder, * = intelligent playlist)")
    for p in items:
        count = str(p.count) if p.kind == "playlist" else ""
        print(f"{p.id:>12}  {count:>6} {icon.get(p.kind, '?')} {p.path}")
    return EXIT_OK


def cmd_backups(args) -> int:
    if args.prune is not None:
        if args.prune < 1:
            print("--prune needs a number of backups to keep (1 or more).")
            return EXIT_ERROR
        removed = backup.prune(args.prune)
        print(f"Removed {len(removed)} old backup(s); kept the newest {args.prune}.")
        return EXIT_OK
    items = backup.list_backups()
    if not items:
        print(f"No backups yet. They will be stored in {config.backups_dir()}")
        return EXIT_OK
    print(f"Backups in {config.backups_dir()} (newest first):")
    for bid, mf in items:
        print(f"  {bid}   rekordbox {mf.get('rekordbox_version') or '?':<9} {mf.get('reason', '')}")
    print("\nRestore one with:  rbsync restore <id>   or   rbsync restore latest")
    keep = config.keep_backups()
    print(f"The newest {keep} are kept automatically (RBSYNC_KEEP_BACKUPS)." if keep
          else "All backups are kept (RBSYNC_KEEP_BACKUPS=0).")
    return EXIT_OK


def cmd_restore(args) -> int:
    from .rekordbox import Library, RekordboxError, default_db_path, is_running

    out = Output()
    out(f"=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  rbsync {__version__}  RESTORE {args.backup}")
    try:
        bid, mf = backup.resolve(args.backup)
        db_path = args.db or default_db_path()
        if not db_path:
            raise RekordboxError("Could not find your rekordbox library. Pass --db PATH.")
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if os.path.normcase(os.path.abspath(mf.get("db_dir", db_dir))) != os.path.normcase(db_dir):
            out(f"Note: this backup was taken from {mf.get('db_dir')}")
        out(f"Restore backup {bid} ({mf.get('created')}, {mf.get('reason')})")
        out(f"into {db_dir}?")
        if not args.yes and not _confirm("Replace the current rekordbox library database with this backup?"):
            out("Cancelled. Nothing was changed.")
            return EXIT_BLOCKED
        if is_running():
            if args.yes or not _wait_for_rekordbox_to_close(out):
                out("BLOCKED: quit rekordbox before restoring.")
                return EXIT_BLOCKED
        version = config.rekordbox_version(db_dir)
        with Lock():
            bid, safety = backup.restore(bid, db_dir, version)
        out(f"Restored {bid}. The state before the restore was saved as {os.path.basename(safety)}.")
        with Library(db_path) as lib:
            out(f"Library opens fine: {len(lib.collection())} tracks, {len(lib.playlists())} playlists/folders.")
        return EXIT_OK
    except LockedError as e:
        out(f"BLOCKED: {e}")
        return EXIT_BLOCKED
    except (FileNotFoundError, RekordboxError) as e:
        out(f"ERROR: {e}")
        return EXIT_ERROR
    finally:
        out.write_log()


def _latest_release(timeout: float = 3.0) -> Optional[str]:
    """Latest published rbsync version on GitHub, or None when offline."""
    import urllib.request

    url = "https://api.github.com/repos/YasiSaps/rekordbox-playlist-sync/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"rbsync/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r).get("tag_name", "").lstrip("v") or None
    except Exception:
        return None


def _newer(latest: str, current: str) -> bool:
    def parts(v):
        return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))

    return parts(latest) > parts(current)


def cmd_doctor(args) -> int:
    ok = True
    latest = None if args.offline else _latest_release()
    if latest and _newer(latest, __version__):
        print(f"rbsync        {__version__}  (update available: {latest} - run the installer again)")
    else:
        print(f"rbsync        {__version__}")
    print(f"Python        {platform.python_version()} ({sys.executable})")
    print(f"System        {platform.system()} {platform.release()} {platform.machine()}")
    try:
        import pyrekordbox

        print(f"pyrekordbox   {getattr(pyrekordbox, '__version__', 'installed')}")
    except ImportError:
        print("pyrekordbox   NOT INSTALLED  -> pip install pyrekordbox")
        return EXIT_ERROR
    from .rekordbox import Library, RekordboxError, default_db_path, is_running

    db_path = args.db or default_db_path()
    print(f"Library       {db_path or 'NOT FOUND'}")
    if not db_path:
        return EXIT_ERROR
    version = config.rekordbox_version(os.path.dirname(db_path))
    status = "verified" if config.is_tested(version) else "NOT verified - apply needs --allow-untested"
    print(f"rekordbox     {version or 'unknown'} ({status})")
    running = is_running()
    print(f"Running       {'yes - quit it before apply/restore' if running else 'no'}")
    try:
        with Library(db_path) as lib:
            print(f"Database      opens OK: {len(lib.collection())} tracks, "
                  f"{sum(1 for p in lib.playlists() if p.kind == 'playlist')} playlists")
    except RekordboxError as e:
        print(f"Database      ERROR: {e}")
        ok = False
    try:
        os.makedirs(config.backups_dir(), exist_ok=True)
        print(f"Backups       {config.backups_dir()} (writable)")
    except OSError as e:
        print(f"Backups       ERROR: {e}")
        ok = False
    print(f"Change log    {config.log_path()}")
    if Lock().owner():
        print(f"Lock          {os.path.join(config.home(), 'rbsync.lock')} "
              "(another rbsync is running, or left over from a crash - removed automatically)")
    return EXIT_OK if ok else EXIT_ERROR


def cmd_selftest(args) -> int:
    from . import selftest

    return selftest.run(args.db)


def cmd_integrate(args) -> int:
    from . import integrate

    try:
        print(integrate.uninstall() if args.remove else integrate.install())
        return EXIT_OK
    except Exception as e:
        print(f"ERROR: {e}")
        return EXIT_ERROR


# --- parser -----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rbsync", description=DESCRIPTION, epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"rbsync {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    def common(sp, writes: bool):
        sp.add_argument("file", help="M3U or M3U8 file with the playlist's desired contents")
        sp.add_argument("--playlist", metavar="NAME",
                        help="rekordbox playlist name (default: the file name without extension)")
        sp.add_argument("--playlist-id", metavar="ID",
                        help="rekordbox playlist ID, if several playlists share the name")
        sp.add_argument("--create", action="store_true",
                        help="create the playlist if it does not exist yet")
        sp.add_argument("--folder", metavar="NAME",
                        help="with --create: put the new playlist in this folder (created if "
                             "needed; 'Gigs / 2026' for a sub-folder path that already exists)")
        sp.add_argument("--reorder", action="store_true",
                        help="also reorder the playlist to match the file's order")
        sp.add_argument("--case-sensitive", action="store_true",
                        help="treat paths differing only in letter case as different files")
        sp.add_argument("--db", metavar="PATH", help="path to master.db (default: auto-detect)")
        if writes:
            sp.add_argument("--strict", action="store_true",
                            help="refuse to write if any line of the file could not be used")
            sp.add_argument("--allow-untested", action="store_true",
                            help="write even if this rekordbox version has not been verified")

    sp = sub.add_parser("plan", help="show what would change (dry run, safe any time)")
    common(sp, writes=False)
    sp.add_argument("--json", action="store_true", help="machine-readable output")
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("apply", help="write the changes (rekordbox must be closed)")
    common(sp, writes=True)
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser("sync", help="interactive: preview, confirm, wait for rekordbox to close, apply")
    common(sp, writes=True)
    sp.add_argument("--pause", action="store_true", help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_sync)

    sp = sub.add_parser("playlists", help="list your rekordbox playlists and their IDs")
    sp.add_argument("--db", metavar="PATH")
    sp.set_defaults(func=cmd_playlists)

    sp = sub.add_parser("backups", help="list the library backups rbsync has made")
    sp.add_argument("--prune", type=int, metavar="N", help="delete all but the newest N backups")
    sp.set_defaults(func=cmd_backups)

    sp = sub.add_parser("restore", help="put a backup back (undo)")
    sp.add_argument("backup", nargs="?", default="latest", help="backup id, or 'latest' (default)")
    sp.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    sp.add_argument("--db", metavar="PATH")
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("doctor", help="check your setup (and whether an update is available)")
    sp.add_argument("--db", metavar="PATH")
    sp.add_argument("--offline", action="store_true", help="skip the update check")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("selftest", help="end-to-end test on a temporary copy of your library")
    sp.add_argument("--db", metavar="PATH")
    sp.set_defaults(func=cmd_selftest)

    sp = sub.add_parser("integrate", help="add a drag-and-drop app (macOS) or Send-to entry (Windows)")
    sp.add_argument("--remove", action="store_true", help="remove it again")
    sp.set_defaults(func=cmd_integrate)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    return args.func(args)
