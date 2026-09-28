import os

import pytest

from rbsync import lock


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("RBSYNC_HOME", str(tmp_path))
    return tmp_path


def test_acquire_and_release(home):
    with lock.Lock() as held:
        assert held.owner() == os.getpid()
        assert (home / "rbsync.lock").exists()
    assert not (home / "rbsync.lock").exists()


def test_other_live_process_blocks(home, monkeypatch):
    (home / "rbsync.lock").write_text("424242")
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: True)
    with pytest.raises(lock.LockedError):
        lock.Lock().acquire()
    assert (home / "rbsync.lock").read_text() == "424242"  # not ours to remove


def test_stale_lock_taken_over(home, monkeypatch):
    (home / "rbsync.lock").write_text("424242")
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: False)
    with lock.Lock() as held:
        assert held.owner() == os.getpid()


def test_garbage_lock_taken_over(home):
    (home / "rbsync.lock").write_text("not a pid")
    with lock.Lock():
        pass
