# How rbsync works (and why re-importing M3U files re-copies your USB)

This page explains what rekordbox does with playlists and USB exports, what we verified, and
exactly what rbsync changes.

## How rekordbox identifies tracks

- Your library lives in an encrypted SQLite database, `master.db`
  (macOS: `~/Library/Pioneer/rekordbox/`, Windows: `%APPDATA%\Pioneer\rekordbox\`).
- Every track in the **collection** is a row (`djmdContent`) with its own **ID** and **UUID**. The
  row stores the file path (`FolderPath`) and links to its hot cues, memory cues, beatgrid,
  analysis files, My Tags, rating and colour.
- A **playlist** (`djmdPlaylist`) is a list of rows in `djmdSongPlaylist`, each pointing at a
  track **ID**, with a track number for the order.
- When you import a file (drag & drop, M3U, XML), rekordbox matches it to an existing collection
  row **by exact path**. If the path is spelled differently — other letter case, other Unicode
  normalization, a `file://` URL — it becomes a **new collection row**: no cues, no grid edits,
  new ID. We found real libraries containing the same file twice for exactly this reason
  (`Track - ARTIST.mp3` with 1 cue and `Track - Artist.mp3` with 6 cues).

## What M3U import does

**File → Import → Import Playlist** always **adds a new playlist**. There is no option to
update or merge into an existing one, and rekordbox allows several playlists with the same name
side by side, so giving the file the same name does not make it "the same playlist".
The only way to replace a playlist with M3U import is delete + re-import.

Other official routes don't help either:

| Route | Updates an existing playlist in place? | Notes |
|---|---|---|
| M3U/M3U8/PLS import | No — always a new playlist | Path mismatches create new, unanalysed tracks |
| rekordbox XML import | No — imports as a playlist | XML cannot carry My Tags; importing tracks can overwrite track info |
| Intelligent playlists | Updates itself, but from rules/tags inside rekordbox | Can't be driven by an external file |
| Public API | None exists for editing playlists | — |

## Why the USB gets re-copied

rekordbox does not document how Sync Manager decides what to copy. What we observed, and what
matches other users' reports:

- Sync Manager works **per playlist**. A playlist that disappears is removed from the USB,
  together with tracks no other synced playlist uses. A playlist that appears is pushed with
  all its tracks.
- Delete + re-import therefore looks like "remove playlist A, add playlist B", even when B
  contains almost the same tracks.
- Tracks that came back as **new collection rows** (path spelling mismatch) are new tracks as far
  as the USB is concerned and are copied again.

## What rbsync does instead

1. Reads your M3U/M3U8 (UTF-8, UTF-8 BOM or Windows-1252; absolute, relative, `file://` and UNC
   paths).
2. Normalizes every path (NFC Unicode, `/` separators, case-folded) and matches it against the
   collection, so spelling variants resolve to the track you already have. If a file is in the
   collection twice, the row with the most cues wins.
3. Reads the **existing** playlist and computes the difference: rows to remove, tracks to add,
   unchanged rows. Nothing else.
4. With `apply`: refuses if rekordbox is running, checks the rekordbox version, backs up the
   database, then deletes and inserts only the changed `djmdSongPlaylist` rows (and optionally
   renumbers them for `--reorder`) through [pyrekordbox](https://github.com/dylanljones/pyrekordbox),
   which also maintains rekordbox's update sequence numbers and `masterPlaylists6.xml`.
5. Re-reads the playlist and verifies it matches the file exactly.

Because the playlist ID and every track ID stay the same, Sync Manager sees a playlist with a few
tracks added and removed, and only transfers those.

## Verified result

Test on macOS, rekordbox 7.2.19, a 115 GB USB with 2,038 audio files:

| Step | Result |
|---|---|
| Playlist changed with rbsync: keep 3, remove 2, add 3 | Same playlist ID; cues intact; collection unchanged |
| Sync Manager → USB | **3 files added, 0 deleted, 0 of 2,038 existing files re-written** (checked by inode, size and mtime) |
| Removed tracks | Stayed on the USB because other synced playlists still use them |

Reproduce it on your own setup with [TESTING.md](TESTING.md).
