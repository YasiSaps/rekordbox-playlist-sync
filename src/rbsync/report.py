"""Human-readable change report."""

from __future__ import annotations

from typing import List

from .planner import Plan


def render(plan: Plan, reorder: bool = False, verbose: bool = True) -> List[str]:
    out = []
    if plan.create:
        out.append(f'Playlist: "{plan.playlist_name}" (new, will be created)')
    else:
        out.append(
            f'Playlist: "{plan.playlist_name}" (ID {plan.playlist_id}, '
            f"{len(plan.keep) + len(plan.remove)} tracks now)"
        )
    out.append(f"Playlist file: {len(plan.desired)} tracks found in your rekordbox collection")
    out.append("")
    out.append("PLAYLIST CHANGES  (rekordbox database only - no music files are touched)")
    out.append(f"  + add        {len(plan.add)}")
    if verbose:
        out += [f"      + {t.label}" for t in plan.add]
    out.append(f"  - remove     {len(plan.remove)}   (removed from this playlist only; "
               "the track stays in your collection)")
    if verbose:
        out += [f"      - {e.track.label if e.track else 'missing track ' + e.song_id}"
                for e in plan.remove]
    out.append(f"  = unchanged  {len(plan.keep)}")
    if reorder:
        out.append(f"  ~ reorder    {'yes' if plan.reorder_needed else 'already in order'}")
    elif plan.reorder_needed and plan.keep:
        out.append("  (order differs from the file; add --reorder to match it)")

    if plan.not_in_collection:
        out.append("")
        out.append(f"NOT IN YOUR REKORDBOX COLLECTION ({len(plan.not_in_collection)}) - skipped.")
        out.append("  Add these files to rekordbox once so they get analysed, then run rbsync again:")
        out += [f"      ? {p}" for p in plan.not_in_collection]
    if plan.missing_files:
        out.append("")
        out.append(f"FILE NOT FOUND ON DISK ({len(plan.missing_files)}) - skipped:")
        out += [f"      ! {p}" for p in plan.missing_files]
    if plan.offline:
        out.append("")
        out.append(f"WARNING: {len(plan.offline)} track(s) are in your collection but their file is "
                   "missing on disk (moved, renamed or on an unplugged drive).")
        out.append("  They are kept in the playlist, but rekordbox cannot play or export them:")
        out += [f"      ! {t.path}" for t in plan.offline]
    if plan.duplicate_lines:
        out.append("")
        out.append(f"Duplicate lines in the playlist file ignored: {len(plan.duplicate_lines)}")
    if plan.collection_duplicates:
        out.append("")
        out.append(f"NOTE: {len(plan.collection_duplicates)} file(s) are in your collection more than "
                   "once (same file, different path spelling). Using the copy with the most cues:")
        out += [f"      * {used.path}  (ID {used.id}, {used.cues} cues)"
                for used, _ in plan.collection_duplicates]
    if plan.skipped:
        out.append("")
        out.append(f"SUMMARY: {plan.skipped} line(s) of the playlist file were skipped (see above). "
                   "The rest will be applied; use --strict to refuse instead.")
    return out
