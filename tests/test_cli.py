import pytest

from rbsync import cli


def test_help_and_version(capsys):
    assert cli.main([]) == 0
    assert "rekordbox" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0


@pytest.mark.parametrize("cmd", ["plan", "apply", "sync"])
def test_commands_parse(cmd):
    args = cli.build_parser().parse_args([cmd, "Set.m3u8", "--reorder", "--create", "--folder", "Gigs"])
    assert args.file == "Set.m3u8" and args.reorder and args.create and args.folder == "Gigs"


def test_playlist_name_candidates():
    parse = cli.build_parser().parse_args
    args = parse(["plan", "/x/Peak Time – Late.m3u8"])
    assert cli._name_candidates(args, None) == ["Peak Time – Late"]
    assert cli._name_candidates(args, "Friday Peak") == ["Friday Peak", "Peak Time – Late"]
    assert cli._name_candidates(args, "Peak Time – Late") == ["Peak Time – Late"]
    args = parse(["plan", "/x/a.m3u8", "--playlist", "Chosen"])
    assert cli._name_candidates(args, "Friday Peak") == ["Chosen"]


def test_write_only_flags():
    parse = cli.build_parser().parse_args
    assert parse(["apply", "a.m3u8", "--strict"]).strict
    with pytest.raises(SystemExit):
        parse(["plan", "a.m3u8", "--strict"])


def test_version_compare():
    assert cli._newer("0.10.0", "0.9.1")
    assert cli._newer("0.2.0", "0.1.0")
    assert not cli._newer("0.1.0", "0.1.0")


def test_backups_prune(tmp_path, monkeypatch, capsys):
    from rbsync import backup

    monkeypatch.setenv("RBSYNC_HOME", str(tmp_path / "home"))
    db = tmp_path / "db"
    db.mkdir()
    (db / "master.db").write_bytes(b"x")
    for _ in range(4):
        backup.create(str(db), "test")
    assert cli.main(["backups", "--prune", "2"]) == 0
    assert len(backup.list_backups()) == 2
    assert cli.main(["backups", "--prune", "0"]) == 1


def test_windows_send_to_handles_every_file():
    from rbsync import integrate

    script = integrate._sendto_script(r"C:\Users\DJ\AppData\Local\rbsync\venv\Scripts\python.exe")
    assert "shift" in script and "goto next" in script and script.count("rbsync sync") == 1
    assert "--pause" not in script and script.rstrip().endswith("pause")
