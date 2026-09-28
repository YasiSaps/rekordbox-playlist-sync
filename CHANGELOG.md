# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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

[0.1.0]: https://github.com/YasiSaps/rekordbox-playlist-sync/releases/tag/v0.1.0
