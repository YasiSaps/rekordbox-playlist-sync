# Test rbsync with your own library and USB

Do this once with a small playlist before using rbsync on the playlists you play out.

## 1. Self test (no risk)

```bash
rbsync selftest
```

This copies your library to a temporary folder and runs create → add/remove → no-op → reorder →
restore on the **copy**. Your real library is not modified. You should see `RESULT: PASS`.

## 2. Small real playlist + USB

1. In rekordbox, make a playlist called **RBSYNC TEST** with 5 tracks that are already analysed.
2. Sync it to your USB with **Sync Manager**. Quit rekordbox.
3. Create `RBSYNC TEST.m3u8` that keeps 3 of the 5 tracks and adds 3 other tracks from your
   collection. Ideally pick tracks that are **not on the USB yet**, so you can see them arrive.
4. Preview and apply:
   ```bash
   rbsync plan  "RBSYNC TEST.m3u8"
   rbsync apply "RBSYNC TEST.m3u8"
   ```
   Expect `+ add 3`, `- remove 2`, `= unchanged 3`.
5. Take a snapshot of the USB (replace `USB` with your drive name):

   macOS:
   ```bash
   find /Volumes/USB/Contents -type f -exec stat -f '%i %z %m %N' {} + | sort -k4 > before.txt
   ```
   Windows (PowerShell):
   ```powershell
   Get-ChildItem E:\Contents -Recurse -File | Select FullName,Length,LastWriteTimeUtc | Export-Csv before.csv
   ```
6. Open rekordbox, check the playlist (same name, 6 tracks, cues intact), sync with Sync Manager,
   quit rekordbox.
7. Snapshot again (`after.txt` / `after.csv`) and compare:

   macOS:
   ```bash
   diff <(cut -d' ' -f4- before.txt) <(cut -d' ' -f4- after.txt)   # added / removed files
   diff before.txt after.txt | grep '^>' | wc -l                     # files added or rewritten
   ```
   Windows:
   ```powershell
   Compare-Object (Import-Csv before.csv) (Import-Csv after.csv) -Property FullName,Length,LastWriteTimeUtc
   ```

**Pass:** only the 3 new tracks appear; nothing that was already on the USB is rewritten; the 2
removed tracks disappear only if no other synced playlist uses them.

8. Clean up: delete **RBSYNC TEST** in rekordbox and sync once more.

If anything looks wrong: quit rekordbox, run `rbsync restore latest`, and
[open an issue](https://github.com/YasiSaps/rekordbox-playlist-sync/issues/new/choose) with the
output of `rbsync doctor`.
