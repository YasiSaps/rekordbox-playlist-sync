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
    py = python.replace("\\", "\\\\").replace('"', '\\"')
    return f'''
on open theFiles
    repeat with f in theFiles
        set p to POSIX path of f
        set cmd to (quoted form of "{py}") & " -m rbsync sync --pause " & (quoted form of p)
        tell application "Terminal"
            activate
            do script cmd
        end tell
    end repeat
end open

on run
    display dialog "Drop an .m3u or .m3u8 playlist file onto this app to update the rekordbox playlist with the same name. You will see every change and confirm before anything is written." buttons {{"OK"}} default button 1 with title "rbsync"
end run
'''


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
        with open(target, "w", encoding="utf-8") as f:
            f.write("@echo off\r\nchcp 65001 >nul\r\n")
            f.write(f'"{python}" -m rbsync sync --pause "%~1"\r\n')
        return (f"Installed {target}\n"
                'Right-click an .m3u/.m3u8 file > Send to > "rbsync - Update rekordbox playlist". '
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
