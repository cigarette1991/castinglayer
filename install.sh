#!/usr/bin/env bash
# One-step installer for castlayer on macOS.
#   ./install.sh            (from a clone of this repo)
set -euo pipefail

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }

[[ "$(uname)" == "Darwin" ]] || { echo "castlayer only runs on macOS." >&2; exit 1; }

if ! command -v brew >/dev/null 2>&1; then
  say "Installing Homebrew (you may be asked for your Mac password)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi

command -v ffmpeg  >/dev/null 2>&1 || { say "Installing ffmpeg";  brew install ffmpeg; }
command -v python3 >/dev/null 2>&1 || { say "Installing Python"; brew install python; }

APP_DIR="$HOME/.castinglayer"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
say "Installing castlayer into $APP_DIR"
python3 -m venv "$APP_DIR"
"$APP_DIR/bin/python" -m pip install -q --upgrade pip
if [[ -n "$SRC_DIR" && -f "$SRC_DIR/pyproject.toml" ]]; then
  "$APP_DIR/bin/python" -m pip install -q "$SRC_DIR"
else
  "$APP_DIR/bin/python" -m pip install -q "git+https://github.com/cigarette1991/castinglayer.git"
fi

BIN_DIR="$(brew --prefix)/bin"
ln -sf "$APP_DIR/bin/castlayer" "$BIN_DIR/castlayer"

say "Done. Make sure your TV is on, then run:  castlayer"
echo "    (The first time, macOS will ask to allow Screen Recording for your terminal:"
echo "     allow it, quit the terminal with Cmd+Q, reopen it and run castlayer again.)"
