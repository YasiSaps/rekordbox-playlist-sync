"""Desktop integration: a drag-and-drop app on macOS, a "Send to" entry on Windows."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

MAC_APP = "rbsync Playlist Updater.app"
WIN_SENDTO = "rbsync - Update rekordbox playlist.cmd"


def _mac_app_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Applications", MAC_APP)


def _win_sendto_path() -> str:
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(appdata, "Microsoft", "Windows", "SendTo", WIN_SENDTO)


def _applescript(python: str) -> str:
    # Several dropped files run one after another in a single Terminal window (never in
    # parallel), with one "press Enter" at the end.
    py = python.replace("\\", "\\\\").replace('"', '\\"')
    return f'''
on open theFiles
    set base to (quoted form of "{py}") & " -m rbsync sync "
    set cmd to ""
    set n to count of theFiles
    repeat with i from 1 to n
        set p to POSIX path of (item i of theFiles)
        set flag to ""
        if i = n then set flag to "--pause "
        if cmd is not "" then set cmd to cmd & " ; "
        set cmd to cmd & base & flag & (quoted form of p)
    end repeat
    tell application "Terminal"
        activate
        do script cmd
    end tell
end open

on run
    display dialog "Drop one or more .m3u / .m3u8 playlist files onto this app to update the rekordbox playlists with the same names. You will see every change and confirm before anything is written." buttons {{"OK"}} default button 1 with title "rbsync"
end run
'''


def _sendto_script(python: str) -> str:
    # Handles every selected file, one after another.
    return (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        ":next\r\n"
        'if "%~1"=="" goto done\r\n'
        f'"{python}" -m rbsync sync "%~1"\r\n'
        "shift\r\n"
        "goto next\r\n"
        ":done\r\n"
        "echo.\r\n"
        "pause\r\n"
    )


def install() -> str:
    python = sys.executable
    if sys.platform == "darwin":
        target = _mac_app_path()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target):
            shutil.rmtree(target)
        subprocess.run(["osacompile", "-o", target, "-e", _applescript(python)], check=True)
        return (f"Installed {target}\n"
                "Drag an .m3u/.m3u8 onto it, or right-click the file > Open With > "
                f"{MAC_APP[:-4]}. Tip: drag the app into your Dock.")
    if os.name == "nt":
        target = _win_sendto_path()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(_sendto_script(python))
        return (f"Installed {target}\n"
                'Select one or more .m3u/.m3u8 files, right-click > Send to > "rbsync - Update rekordbox playlist". '
                "(On Windows 11 choose 'Show more options' first.)")
    raise RuntimeError("Desktop integration is available on macOS and Windows only.")


def uninstall() -> str:
    target = _mac_app_path() if sys.platform == "darwin" else _win_sendto_path()
    if os.path.isdir(target):
        shutil.rmtree(target)
    elif os.path.exists(target):
        os.remove(target)
    else:
        return "Nothing to remove."
    return f"Removed {target}"
