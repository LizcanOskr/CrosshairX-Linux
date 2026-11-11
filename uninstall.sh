#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "    Desinstalador de CrosshairX para Linux                "
echo "=========================================================="

if [ "$(id -u)" -eq 0 ]; then
    PREFIX="/opt/crosshairx-linux"
    BIN_FILE="/usr/local/bin/crosshairx-linux"
    DESKTOP_FILE="/usr/share/applications/crosshairx-linux.desktop"
    ICON_FILE="/usr/share/icons/hicolor/scalable/apps/crosshairx-linux.svg"
else
    PREFIX="$HOME/.local/share/crosshairx-linux"
    BIN_FILE="$HOME/.local/bin/crosshairx-linux"
    DESKTOP_FILE="$HOME/.local/share/applications/crosshairx-linux.desktop"
    ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/apps/crosshairx-linux.svg"
fi

echo "Eliminando archivos instalados..."
rm -rf "$PREFIX"
rm -f "$BIN_FILE"
rm -f "$DESKTOP_FILE"
rm -f "$ICON_FILE"

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$(dirname "$DESKTOP_FILE")" 2>/dev/null || true
fi

echo ""
echo "¡CrosshairX ha sido desinstalado correctamente!"
