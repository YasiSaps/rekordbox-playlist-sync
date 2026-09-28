# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-09-28

### Fixed
- **Deleted items in the rekordbox database are now ignored.** rekordbox keeps deleted tracks,
  playlists and playlist entries (marked `rb_local_deleted`). 0.1.0 could match a deleted
  track that shared a path with a live one, report a false "N playlists are called …" because
  of a deleted twin, or update a playlist that rekordbox no longer shows.
- Track numbers stay gap-free (1..n over live entries). pyrekordbox counts deleted entries when
  numbering new tracks, which could leave gaps.
- `--folder` with `--create` accepts a path (`"Gigs / 2026"`) and creates missing sub-folders
  instead of one folder with a slash in its name.
- The macOS drop app handles several files one after another in one window instead of opening
  parallel windows; Windows *Send to* now handles every selected file, not just the first.

### Added
- Playlist lookup accepts `"Folder / Name"` paths, tolerates Unicode normalization and letter
  case, recognises intelligent playlists, and suggests close names (*Did you mean…?*).
- `#PLAYLIST:` lines in extended M3U files name the playlist (after `--playlist`, before the
  file name). UTF-16 playlist files (with BOM) are read.
- `--strict` refuses to write if any line of the file was skipped; otherwise a summary line
  says how many were.
- Warning for tracks whose file is missing on disk (offline / moved).
- Lock file so two rbsync runs never write at the same time.
- Backup retention: the newest 30 are kept (`RBSYNC_KEEP_BACKUPS`, `0` keeps all);
  `rbsync backups --prune N`. The change log rotates at 2 MB.
- `rbsync doctor` reports when a newer release exists (`--offline` skips the check).
- Installers install the latest release by default (`RBSYNC_REF` still overrides).
- Integration tests against a real rekordbox-schema database, including deleted rows; CI on
  Python 3.13.

### Changed
- The collection is loaded with two bulk queries instead of one query per track, which is much
  faster on large libraries.

## [0.1.0] - 2026-09-28

First public release.

### Added
- `rbsync plan` / `apply` / `sync`: update an existing rekordbox 6/7 playlist in place from an
  M3U/M3U8 file, adding and removing only the changed tracks; optional `--reorder`,
  `--create`, `--folder`.
- Path matching across Unicode normalization (NFC/NFD), letter case, `file://` URLs, relative,
  Windows and UNC paths; UTF-8, UTF-8 BOM and Windows-1252 playlist files.
- Duplicate handling: duplicate lines ignored, duplicate playlist rows removed, duplicate
  collection entries resolved to the copy with the most cues.
- Safety: dry run, automatic backups, `rbsync restore`, rekordbox-running lock, post-write
  verification, rekordbox version gate (`--allow-untested`), change log.
- `rbsync playlists`, `backups`, `doctor`, `selftest` (end-to-end test on a temporary copy of
  the library) and `plan --json`.
- Desktop integration: drag-and-drop app on macOS, right-click *Send to* on Windows
  (`rbsync integrate`).
- One-line installers for macOS (`install.sh`) and Windows (`install.ps1`).

### Verified
- macOS, rekordbox 7.2.19, USB Sync Manager: a +3/−2 playlist change transferred exactly 3
  files and re-wrote none of the 2,038 existing files.

[0.2.0]: https://github.com/YasiSaps/rekordbox-playlist-sync/releases/tag/v0.2.0
[0.1.0]: https://github.com/YasiSaps/rekordbox-playlist-sync/releases/tag/v0.1.0
