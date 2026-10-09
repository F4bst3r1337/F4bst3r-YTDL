#!/usr/bin/env bash
# Startet den F4bst3r-YTDL (Mac/Linux). "./start.sh update" aktualisiert yt-dlp.
# Fehlende Programme (Python, ffmpeg, Deno) werden automatisch eingerichtet.
set -e
cd "$(dirname "$0")"

SUDO=""
[ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"

install_pkg() {  # install_pkg <apt> <dnf> <pacman> <brew>
  if command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update -qq && $SUDO apt-get install -y $1
  elif command -v dnf >/dev/null 2>&1; then $SUDO dnf install -y $2
  elif command -v pacman >/dev/null 2>&1; then $SUDO pacman -S --noconfirm $3
  elif command -v brew >/dev/null 2>&1; then brew install $4
  else return 1; fi
}

# ---- 1. Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 fehlt und wird installiert (Passwort-Abfrage möglich) ..."
  install_pkg "python3 python3-venv" "python3" "python" "python" || {
    echo "Das ging nicht automatisch. Bitte Python 3 installieren: https://www.python.org/downloads/"; exit 1; }
fi

# ---- 2. Eigene Python-Umgebung mit yt-dlp
if [ ! -x .venv/bin/python ]; then
  echo "Erste Einrichtung, das dauert eine Minute ..."
  if ! python3 -m venv .venv 2>/dev/null; then
    rm -rf .venv
    echo "Das venv-Modul fehlt und wird installiert ..."
    install_pkg "python3-venv" "python3" "python" "python" || { echo "Bitte python3-venv installieren."; exit 1; }
    python3 -m venv .venv
  fi
fi
if ! .venv/bin/python -c "import yt_dlp" >/dev/null 2>&1; then
  echo "yt-dlp wird installiert ..."
  .venv/bin/python -m pip install -U pip >/dev/null 2>&1 || true
  .venv/bin/python -m pip install -U "yt-dlp[default]"
fi

if [ "${1:-}" = "update" ]; then
  echo "Aktualisiere yt-dlp ..."
  .venv/bin/python -m pip install -U "yt-dlp[default]"
  exit 0
fi

# ---- 3. ffmpeg und Deno bei Bedarf in den Ordner bin laden
.venv/bin/python setup_tools.py || true

# ---- 4. F4bst3r-YTDL starten
exec .venv/bin/python server.py --open "$@"
