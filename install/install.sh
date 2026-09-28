#!/usr/bin/env bash
# rbsync installer for macOS.
#   curl -fsSL https://raw.githubusercontent.com/YasiSaps/rekordbox-playlist-sync/main/install/install.sh | bash
# Installs into ~/.rbsync, links ~/.local/bin/rbsync and adds the drag-and-drop app.
set -euo pipefail

REF="${RBSYNC_REF:-main}"
SRC="https://github.com/YasiSaps/rekordbox-playlist-sync/archive/${REF}.zip"
DEST="$HOME/.rbsync"
BIN="$HOME/.local/bin"

say() { printf '\033[1m%s\033[0m\n' "$*"; }

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  say "Python 3.9+ is required."
  echo "On macOS, run:  xcode-select --install   (or install Python from https://www.python.org)"
  echo "Then run this installer again."
  exit 1
fi

say "Installing rbsync ($REF) into $DEST ..."
python3 -m venv "$DEST/venv"
"$DEST/venv/bin/python" -m pip install --quiet --upgrade pip
"$DEST/venv/bin/python" -m pip install --quiet --upgrade "$SRC"

mkdir -p "$BIN"
ln -sf "$DEST/venv/bin/rbsync" "$BIN/rbsync"

case ":$PATH:" in
  *":$BIN:"*) ;;
  *)
    for rc in "$HOME/.zshrc" "$HOME/.bash_profile"; do
      if [ -f "$rc" ] || [ "$rc" = "$HOME/.zshrc" ]; then
        grep -q '# added by rbsync' "$rc" 2>/dev/null || \
          printf '\nexport PATH="$HOME/.local/bin:$PATH"  # added by rbsync\n' >> "$rc"
      fi
    done
    say "Added ~/.local/bin to your PATH. Open a new Terminal window to use 'rbsync'."
    ;;
esac

"$DEST/venv/bin/rbsync" integrate || true
echo
"$DEST/venv/bin/rbsync" doctor || true
echo
say "Done. Try:  rbsync plan \"Your Playlist.m3u8\""
echo "Uninstall: rbsync integrate --remove; rm -rf ~/.rbsync ~/.local/bin/rbsync"
