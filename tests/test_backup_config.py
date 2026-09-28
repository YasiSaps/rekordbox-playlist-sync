import os

import pytest

from rbsync import backup, config


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RBSYNC_HOME", str(tmp_path / "home"))
    db = tmp_path / "rekordbox"
    db.mkdir()
    (db / "master.db").write_bytes(b"v1")
    (db / "master.db-wal").write_bytes(b"wal1")
    (db / "masterPlaylists6.xml").write_text(
        '<?xml version="1.0"?><MASTER_PLAYLIST><PRODUCT Name="rekordbox" Version="7.2.19"/>',
        encoding="utf-8")
    return db


def test_version_detection(env):
    assert config.rekordbox_version(str(env)) == "7.2.19"
    assert config.is_tested("7.2.19") and config.is_tested("7.2")
    assert not config.is_tested("7.3.0") and not config.is_tested("6.8.5") and not config.is_tested(None)
    assert not config.is_tested("7.20.1")


def test_backup_and_restore_roundtrip(env):
    saved = backup.create(str(env), "test", "7.2.19")
    assert sorted(os.listdir(saved)) == ["manifest.json", "master.db", "master.db-wal",
                                         "masterPlaylists6.xml"]
    (env / "master.db").write_bytes(b"v2")
    (env / "master.db-wal").unlink()
    (env / "master.db-shm").write_bytes(b"shm-new")
    bid, safety = backup.restore("latest", str(env))
    assert (env / "master.db").read_bytes() == b"v1"
    assert (env / "master.db-wal").read_bytes() == b"wal1"
    assert not (env / "master.db-shm").exists()          # stale journal removed
    assert open(os.path.join(safety, "master.db"), "rb").read() == b"v2"  # undo-able


def test_list_and_resolve(env):
    a = backup.create(str(env), "first")
    b = backup.create(str(env), "second")
    listed = [bid for bid, _ in backup.list_backups()]
    assert listed[0] == os.path.basename(b) and os.path.basename(a) in listed
    assert backup.resolve("latest")[0] == os.path.basename(b)
    with pytest.raises(FileNotFoundError):
        backup.resolve("nope")


def test_backup_requires_master_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RBSYNC_HOME", str(tmp_path / "home"))
    with pytest.raises(FileNotFoundError):
        backup.create(str(tmp_path), "x")


def test_backups_in_same_millisecond_do_not_collide(env):
    made = {backup.create(str(env), f"burst {i}") for i in range(20)}
    assert len(made) == 20 and len(backup.list_backups()) == 20
