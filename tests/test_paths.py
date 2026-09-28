import unicodedata

from rbsync.paths import is_absolute_any, normalize, path_key


def test_nfc_and_nfd_match():
    nfc = "/Music/Beyoncé - Halo.mp3"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert path_key(nfc) == path_key(nfd)


def test_case_insensitive_by_default():
    assert path_key("/Music/Track - ARTIST.mp3") == path_key("/music/track - Artist.mp3")
    assert path_key("/A.mp3", case_sensitive=True) != path_key("/a.mp3", case_sensitive=True)


def test_windows_separators_and_drive_case():
    assert path_key(r"C:\Users\DJ\Music\Track.mp3") == path_key("c:/users/dj/music/track.mp3")


def test_redundant_separators():
    assert normalize("/Music//House/./Track.mp3") == "/Music/House/Track.mp3"
    assert normalize("/Music/House/../Pop/Track.mp3") == "/Music/Pop/Track.mp3"


def test_unc_paths_keep_double_slash():
    assert normalize(r"\\nas\music\a.mp3") == "//nas/music/a.mp3"


def test_is_absolute_any():
    assert is_absolute_any("/Users/x/a.mp3")
    assert is_absolute_any("C:\\Music\\a.mp3")
    assert is_absolute_any("D:/Music/a.mp3")
    assert is_absolute_any("\\\\server\\share\\a.mp3")
    assert not is_absolute_any("House/a.mp3")
    assert not is_absolute_any("apple-music:tracks:123")
