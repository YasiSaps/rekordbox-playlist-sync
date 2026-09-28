import os

from rbsync import m3u


def test_extm3u_tags_and_comments_skipped():
    text = "#EXTM3U\n#EXTINF:215,Artist - Title\n/Music/a.mp3\n\n# comment\n/Music/b.mp3\n"
    assert m3u.parse(text) == ["/Music/a.mp3", "/Music/b.mp3"]


def test_file_urls():
    assert m3u.parse("file:///Users/dj/My%20Music/a%20b.mp3") == ["/Users/dj/My Music/a b.mp3"]
    assert m3u.parse("file://localhost/Users/dj/a.mp3") == ["/Users/dj/a.mp3"]
    assert m3u.parse("file:///C:/Music/a.mp3") == ["C:/Music/a.mp3"]
    assert m3u.parse("file://nas/share/a.mp3") == ["//nas/share/a.mp3"]


def test_windows_paths():
    assert m3u.parse(r"C:\Users\DJ\Music\Track One.mp3") == ["C:/Users/DJ/Music/Track One.mp3"]


def test_relative_paths_resolved_against_playlist_folder():
    base = os.path.abspath("playlists")
    out = m3u.parse("House/a.mp3\n../Pop/b.mp3", base_dir=base)
    assert out[0].endswith("playlists/House/a.mp3")
    assert out[1].endswith("/Pop/b.mp3") and "playlists" not in out[1]


def test_http_urls_ignored():
    assert m3u.parse("https://example.com/stream.mp3\n/Music/a.mp3") == ["/Music/a.mp3"]


def test_encodings():
    assert m3u.decode("\ufeff/Music/Café.mp3".encode("utf-8")) == "/Music/Café.mp3"
    assert m3u.decode("/Music/Café.mp3".encode("cp1252")) == "/Music/Café.mp3"


def test_unicode_and_spaces_roundtrip(tmp_path):
    p = tmp_path / "Set.m3u8"
    p.write_text("#EXTM3U\n/Music/Let´s Go (Intro Edit).mp3\n/Music/비디오 Club Mix.mp3\n",
                 encoding="utf-8")
    assert m3u.read(str(p)) == ["/Music/Let´s Go (Intro Edit).mp3", "/Music/비디오 Club Mix.mp3"]
