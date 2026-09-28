"""A small, unencrypted rekordbox-style library for integration tests.

It uses pyrekordbox's own table definitions, so the rbsync <-> pyrekordbox code paths run
for real, including soft-deleted rows (rb_local_deleted = 1) like rekordbox 6/7 leaves behind.
"""

import datetime
import os

XML = """<?xml version="1.0" encoding="UTF-8"?>

<MASTER_PLAYLIST Version="3.0.0" AutomaticSync="0">
  <PRODUCT Name="rekordbox" Version="7.2.19" Company="Pioneer DJ"/>
  <PLAYLISTS>
{nodes}
  </PLAYLISTS>
</MASTER_PLAYLIST>
"""

# playlist id -> (name, attribute, parent, deleted)
PLAYLISTS = {
    "10": ("Gigs", 1, "root", 0),
    "11": ("Peak Time", 0, "10", 0),
    "12": ("Warm Up", 0, "root", 0),
    "13": ("Warm Up", 0, "root", 1),  # deleted twin: must not cause ambiguity
    "14": ("Techno", 4, "root", 0),  # intelligent playlist
    "15": ("Old Stuff", 0, "root", 1),  # deleted playlist
    "16": ("Café Del Mar", 0, "root", 0),
}


def music(tmp_path, n):
    return str(tmp_path / "Music" / f"t{n}.mp3")


def _row(model, now, **values):
    """A table row with every column filled in (rekordbox's schema is mostly NOT NULL)."""
    for col in model.__table__.columns:
        if col.key in values:
            continue
        py = getattr(col.type, "impl", col.type).__class__.__name__.lower()
        if "date" in py or "time" in py or "date" in col.key or col.key.endswith("_at"):
            values[col.key] = now
        elif "int" in py or "float" in py or "numeric" in py or "bool" in py:
            values[col.key] = 0
        else:
            values[col.key] = ""
    return model(**values)


def make(tmp_path):
    """Create the library in tmp_path/rb and return the master.db path.

    Tracks 1..8 are live; track 9 is soft-deleted and shares its path with live track 3.
    "Peak Time" holds 1, 2, 3 plus a soft-deleted row (track 4) and a row pointing at the
    deleted track 9. "Old Stuff" (deleted) has deleted rows only.
    """
    from pyrekordbox.db6 import tables as T
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    rb = tmp_path / "rb"
    rb.mkdir()
    (tmp_path / "Music").mkdir()
    for n in range(1, 9):
        open(music(tmp_path, n), "wb").close()
    db_path = str(rb / "master.db")
    engine = create_engine(f"sqlite:///{db_path}")
    # Like rekordbox's own schema, columns accept NULL (pyrekordbox's models say NOT NULL).
    from sqlalchemy import MetaData

    schema = MetaData()
    for table in T.Base.metadata.sorted_tables:
        copy = table.to_metadata(schema)
        for col in copy.columns:
            if not col.primary_key:
                col.nullable = True
    schema.create_all(engine)
    now = datetime.datetime(2026, 1, 1)
    with Session(engine) as s:
        s.add(_row(T.AgentRegistry, now, registry_id="localUpdateCount", int_1=100))
        s.add(_row(T.DjmdArtist, now, ID="500", Name="Artist", rb_local_deleted=0))
        for n in range(1, 10):
            path = music(tmp_path, 3 if n == 9 else n)
            s.add(_row(T.DjmdContent, now, ID=str(n), UUID=f"uuid-{n}", FolderPath=path, Title=f"T{n}",
                                ArtistID="500", rb_local_deleted=1 if n == 9 else 0))
        s.add(_row(T.DjmdCue, now, ID="c1", ContentID="9", rb_local_deleted=0))  # deleted track
        s.add(_row(T.DjmdCue, now, ID="c2", ContentID="3", rb_local_deleted=0))
        s.add(_row(T.DjmdCue, now, ID="c3", ContentID="3", rb_local_deleted=1))  # deleted cue
        for pid, (name, attr, parent, deleted) in PLAYLISTS.items():
            s.add(_row(T.DjmdPlaylist, now, ID=pid, Seq=int(pid), Name=name, Attribute=attr, ParentID=parent,
                                 UUID=f"pl-{pid}", rb_local_deleted=deleted))
        rows = [("s1", "11", "1", 1, 0), ("s2", "11", "2", 2, 0), ("sx", "11", "4", 3, 1),
                ("s3", "11", "3", 4, 0), ("s9", "11", "9", 5, 0),
                ("o1", "15", "5", 1, 1), ("o2", "15", "6", 2, 1),
                ("w1", "12", "7", 1, 0)]
        for sid, pl, content, no, deleted in rows:
            s.add(_row(T.DjmdSongPlaylist, now, ID=sid, PlaylistID=pl, ContentID=content, TrackNo=no,
                                     UUID=f"sp-{sid}", rb_local_deleted=deleted))
        s.commit()
    nodes = "\n".join(
        f'    <NODE Id="{int(pid):X}" ParentId="{0 if parent == "root" else int(parent):X}" '
        f'Attribute="{attr}" Timestamp="0" Lib_Type="0" CheckType="0"/>'
        for pid, (_, attr, parent, deleted) in PLAYLISTS.items() if not deleted
    )
    with open(rb / "masterPlaylists6.xml", "w", encoding="utf-8") as f:
        f.write(XML.format(nodes=nodes))
    return db_path


def not_running(monkeypatch):
    """Pretend rekordbox is closed, whatever the test machine is doing."""
    from pyrekordbox.db6 import database

    from rbsync import rekordbox

    monkeypatch.setattr(rekordbox, "is_running", lambda: False)
    monkeypatch.setattr(database, "get_rekordbox_pid", lambda: 0)


__all__ = ["make", "music", "not_running", "os"]
