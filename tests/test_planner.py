import unicodedata

from rbsync.planner import Entry, Track, build_plan, index_collection

COLL = [Track(str(i), f"/Music/t{i}.mp3", title=f"T{i}", cues=1) for i in range(1, 11)]


def entries(ids):
    return [Entry(f"s{n}", n, COLL[i - 1]) for n, i in enumerate(ids, start=1)]


def plan(paths, current_ids, **kw):
    return build_plan("Set", "99", paths, COLL, entries(current_ids),
                      exists=kw.pop("exists", lambda p: False), **kw)


def ids(tracks):
    return [t.id for t in tracks]


def test_incremental_add_and_remove():
    p = plan([f"/Music/t{i}.mp3" for i in (1, 2, 3, 6, 7, 8)], [1, 2, 3, 4, 5])
    assert ids(p.add) == ["6", "7", "8"]
    assert [e.song_id for e in p.remove] == ["s4", "s5"]
    assert len(p.keep) == 3 and p.changed


def test_no_changes_is_noop():
    p = plan([f"/Music/t{i}.mp3" for i in (1, 2, 3)], [1, 2, 3])
    assert not p.changed and not p.reorder_needed


def test_reorder_detected_but_membership_unchanged():
    p = plan([f"/Music/t{i}.mp3" for i in (3, 1, 2)], [1, 2, 3])
    assert not p.changed and p.reorder_needed


def test_path_spelling_variants_match_existing_tracks():
    paths = ["/MUSIC/T1.MP3", unicodedata.normalize("NFD", "/Music/t2.mp3"), "\\Music\\t3.mp3"]
    p = plan(paths, [1, 2, 3])
    assert not p.changed


def test_duplicate_lines_and_duplicate_playlist_rows():
    p = plan(["/Music/t1.mp3", "/music/T1.mp3", "/Music/t2.mp3"], [1, 1, 2])
    assert p.duplicate_lines == ["/music/T1.mp3"]
    assert [e.song_id for e in p.remove] == ["s2"]
    assert not p.add


def test_unknown_files_are_reported_not_added():
    p = plan(["/Music/t1.mp3", "/New/sample.wav", "/Gone/x.mp3"], [1],
             exists=lambda path: path.startswith("/New"))
    assert p.not_in_collection == ["/New/sample.wav"]
    assert p.missing_files == ["/Gone/x.mp3"]
    assert not p.changed


def test_create_new_playlist():
    p = build_plan("New", None, ["/Music/t1.mp3"], COLL, [], create=True, exists=lambda _: False)
    assert p.create and ids(p.add) == ["1"]


def test_collection_duplicates_prefer_most_cues():
    coll = [Track("a", "/Music/X.mp3", cues=1), Track("b", "/music/x.mp3", cues=6)]
    best, dupes = index_collection(coll)
    assert best["/music/x.mp3"].id == "b" and len(dupes) == 1


def test_non_file_collection_entries_ignored():
    coll = [Track("a", "apple-music:tracks:123"), Track("b", "C:/Music/a.mp3")]
    best, _ = index_collection(coll)
    assert list(best) == ["c:/music/a.mp3"]


def test_orphaned_playlist_rows_removed():
    current = entries([1]) + [Entry("sx", 2, None)]
    p = build_plan("Set", "99", ["/Music/t1.mp3"], COLL, current, exists=lambda _: False)
    assert [e.song_id for e in p.remove] == ["sx"]


def test_to_dict_is_json_serialisable():
    import json

    json.dumps(plan(["/Music/t1.mp3", "/Music/t9.mp3"], [1, 2]).to_dict())


def test_offline_tracks_are_kept_but_reported():
    on_disk = {"/Music/t1.mp3"}
    p = plan(["/Music/t1.mp3", "/Music/t2.mp3"], [1], exists=lambda x: x in on_disk)
    assert ids(p.add) == ["2"] and ids(p.offline) == ["2"]
    assert p.skipped == 0


def test_skipped_counts_unusable_lines():
    p = plan(["/Music/t1.mp3", "/Music/new.mp3", "/Gone/x.mp3"], [1],
             exists=lambda x: x == "/Music/new.mp3")
    assert p.skipped == 2 and p.not_in_collection == ["/Music/new.mp3"]
