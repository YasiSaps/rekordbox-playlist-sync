"""A lock file so two rbsync processes never write to the library at the same time
(for example two playlist files dropped on the app at once)."""

from __future__ import annotations

import os
from typing import Optional

from . import config


class LockedError(Exception):
    pass


def _path() -> str:
    return os.path.join(config.home(), "rbsync.lock")


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:  # pragma: no cover - psutil ships with pyrekordbox
        return True


class Lock:
    """Context manager. Raises LockedError if another live rbsync process holds it;
    a lock left behind by a crashed process is taken over."""

    def __init__(self):
        self.path = _path()
        self.held = False

    def owner(self) -> Optional[int]:
        try:
            with open(self.path, encoding="ascii") as f:
                return int(f.read().strip() or 0) or None
        except (OSError, ValueError):
            return None

    def acquire(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                pid = self.owner()
                if pid and pid != os.getpid() and _pid_alive(pid):
                    raise LockedError(
                        f"another rbsync (process {pid}) is updating rekordbox right now. "
                        "Wait for it to finish, then try again."
                    )
                try:
                    os.remove(self.path)  # stale: its process is gone
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="ascii") as f:
                f.write(str(os.getpid()))
            self.held = True
            return self
        raise LockedError(f"could not create the lock file {self.path}")

    def release(self):
        if self.held:
            try:
                os.remove(self.path)
            except FileNotFoundError:
                pass
            self.held = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
