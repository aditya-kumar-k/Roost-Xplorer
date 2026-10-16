#!/usr/bin/env bash
# Remove what ./install.sh added. Your settings are kept unless you pass --purge.
#
#   ./uninstall.sh            remove the launcher, app-menu entry and icon
#   ./uninstall.sh --purge    ...and also delete your saved settings (favorites, labels, tabs)
set -euo pipefail

APP_ID="io.github.aditya_kumar_k.RoostXplorer"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    -h|--help) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

rm -f "$HOME/.local/bin/roost-xplorer" \
      "$DATA_HOME/applications/$APP_ID.desktop" \
      "$DATA_HOME/icons/hicolor/scalable/apps/$APP_ID.svg"
update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true

if [ "$PURGE" = 1 ]; then
  rm -f "$CONFIG_HOME/roost-xplorer.json"
  echo "Removed the launcher, menu entry, icon and your saved settings."
else
  echo "Removed the launcher, menu entry and icon. Your settings were kept in $CONFIG_HOME/roost-xplorer.json (use --purge to delete them)."
fi

if command -v xdg-mime >/dev/null 2>&1 && [ "$(xdg-mime query default inode/directory 2>/dev/null)" = "$APP_ID.desktop" ]; then
  echo "Note: Roost Xplorer is still set as your default folder opener. Pick another one, for example:"
  echo "  xdg-mime default org.gnome.Nautilus.desktop inode/directory   (or org.kde.dolphin.desktop, thunar.desktop, ...)"
fi
