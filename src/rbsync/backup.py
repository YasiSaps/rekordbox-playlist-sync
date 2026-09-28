"""Backups of the rekordbox library database, and restoring them.

Only rekordbox's database files are copied. Music files are never backed up, moved or
deleted by rbsync.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
from typing import List, Optional, Tuple

from . import config

DB_FILES = ("master.db", "master.db-wal", "master.db-shm", "masterPlaylists6.xml")


def create(db_dir: str, reason: str, rekordbox_version: Optional[str] = None) -> str:
    """Copy the library database files into a new timestamped backup folder."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    dest = os.path.join(config.backups_dir(), stamp)
    os.makedirs(dest, exist_ok=False)
    copied = []
    for name in DB_FILES:
        src = os.path.join(db_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, name))
            copied.append(name)
    if "master.db" not in copied:
        shutil.rmtree(dest)
        raise FileNotFoundError(f"No master.db found in {db_dir}")
    manifest = {
        "id": stamp,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "db_dir": db_dir,
        "rekordbox_version": rekordbox_version,
        "files": copied,
    }
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return dest


def list_backups() -> List[Tuple[str, dict]]:
    """All backups, newest first."""
    root = config.backups_dir()
    if not os.path.isdir(root):
        return []
    out = []
    for name in os.listdir(root):
        mf = os.path.join(root, name, "manifest.json")
        if os.path.isfile(mf):
            try:
                with open(mf, encoding="utf-8") as f:
                    out.append((name, json.load(f)))
            except (OSError, ValueError):
                continue
    return sorted(out, key=lambda x: x[0], reverse=True)


def resolve(backup_id: str) -> Tuple[str, dict]:
    backups = list_backups()
    if not backups:
        raise FileNotFoundError("There are no rbsync backups yet.")
    if backup_id in ("latest", "last"):
        return backups[0]
    for bid, mf in backups:
        if bid == backup_id or bid.startswith(backup_id):
            return bid, mf
    raise FileNotFoundError(f"No backup called '{backup_id}'. Run 'rbsync backups' to list them.")


def restore(backup_id: str, db_dir: str, rekordbox_version: Optional[str] = None) -> Tuple[str, str]:
    """Put a backup back in place. The current state is backed up first, so a restore can
    itself be undone. Returns (restored backup id, safety backup path)."""
    bid, manifest = resolve(backup_id)
    src = os.path.join(config.backups_dir(), bid)
    safety = create(db_dir, f"automatic safety copy before restoring {bid}", rekordbox_version)
    for name in DB_FILES:
        live = os.path.join(db_dir, name)
        saved = os.path.join(src, name)
        if os.path.exists(saved):
            shutil.copy2(saved, live)
        elif name != "masterPlaylists6.xml" and os.path.exists(live):
            # A write-ahead log that did not exist when the backup was taken belongs to the
            # newer state and must not be replayed on top of the restored database.
            os.remove(live)
    return bid, safety
