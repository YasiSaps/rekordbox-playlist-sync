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


def test_playlist_name_from_file():
    args = cli.build_parser().parse_args(["plan", "/x/Peak Time – Late.m3u8"])
    assert cli._playlist_name(args) == "Peak Time – Late"
