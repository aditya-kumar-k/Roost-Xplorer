#!/usr/bin/env bash
# Install Roost Xplorer for the current user. No root needed; nothing is copied outside your home folder.
#
#   ./install.sh                 install the launcher, app-menu entry and icon
#   ./install.sh --set-default   ...and also make it the app that opens folders
#   ./install.sh --help
#
# Roost Xplorer runs straight from this folder, so keep the folder where it is after installing.
# To remove everything again: ./uninstall.sh
set -euo pipefail

APP_ID="io.github.aditya_kumar_k.RoostXplorer"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/roost_xplorer.py"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
SET_DEFAULT=0

for arg in "$@"; do
  case "$arg" in
    --set-default) SET_DEFAULT=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }

# ---- 1. check that the toolkit is installed and recent enough ---------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  warn "Python 3 is required but was not found."; exit 1
fi

if ! python3 - <<'PY' 2>/dev/null
import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
ok = (sys.version_info >= (3, 12)
      and (Gtk.get_major_version(), Gtk.get_minor_version()) >= (4, 12)
      and (Adw.get_major_version(), Adw.get_minor_version()) >= (1, 5))
sys.exit(0 if ok else 2)
PY
then
  warn "Roost Xplorer needs Python 3.12 or newer with PyGObject, GTK 4.12 or newer and libadwaita 1.5 or newer."
  warn "Install them for your distribution:"
  . /etc/os-release 2>/dev/null || true
  case "${ID:-} ${ID_LIKE:-}" in
    *fedora*|*rhel*) warn "  sudo dnf install python3-gobject gtk4 libadwaita" ;;
    *debian*|*ubuntu*) warn "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1" ;;
    *arch*) warn "  sudo pacman -S python-gobject gtk4 libadwaita" ;;
    *suse*) warn "  sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 libadwaita" ;;
    *) warn "  (PyGObject, GTK 4 and libadwaita, with their GObject introspection data)" ;;
  esac
  warn "Older systems (for example Debian 12 or Ubuntu 22.04) ship a Python or libadwaita that is too old."
  exit 1
fi

# ---- 2. install ----------------------------------------------------------------------------------
chmod +x "$SCRIPT"
mkdir -p "$BIN_DIR" "$APPS_DIR" "$ICON_DIR"

ln -sf "$SCRIPT" "$BIN_DIR/roost-xplorer"
cp "$HERE/assets/icons/hicolor/scalable/apps/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"

cat > "$APPS_DIR/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Roost Xplorer
GenericName=File Manager
Comment=A sleek, dark file manager
Exec="$SCRIPT" %U
Icon=$APP_ID
Terminal=false
Categories=System;FileTools;FileManager;GTK;
MimeType=inode/directory;
StartupWMClass=$APP_ID
DESKTOP

update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true

if [ "$SET_DEFAULT" = 1 ]; then
  if command -v xdg-mime >/dev/null 2>&1; then
    xdg-mime default "$APP_ID.desktop" inode/directory
    say "Roost Xplorer is now the default app for opening folders."
  else
    warn "xdg-mime was not found, so the default folder handler was not changed."
  fi
fi

say "Roost Xplorer is installed."
echo "  Start it from your app menu (search for \"Roost Xplorer\"), or run:  roost-xplorer"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "  Note: $BIN_DIR is not in your PATH, so the 'roost-xplorer' command won't be found until you add it."
     warn "  The app-menu entry works regardless." ;;
esac
[ "$SET_DEFAULT" = 1 ] || echo "  To also make it the default folder opener, run:  ./install.sh --set-default"
missing=""
command -v pdftoppm >/dev/null 2>&1 || missing="$missing PDF previews (package: poppler-utils)"
command -v 7z >/dev/null 2>&1 || command -v 7zz >/dev/null 2>&1 || command -v 7za >/dev/null 2>&1 || missing="$missing${missing:+;} opening 7z and rar archives (package: p7zip or 7zip)"
[ -z "$missing" ] || echo "  Optional extras you could install later: $missing."
