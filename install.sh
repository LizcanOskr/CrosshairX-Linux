#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================================="
echo "    Instalador de CrosshairX para Linux (KDE Plasma)      "
echo "=========================================================="
echo ""

# Determinar modo de instalacion
if [ "$(id -u)" -eq 0 ]; then
    INSTALL_MODE="system"
    PREFIX="/opt/crosshairx-linux"
    BIN_DIR="/usr/local/bin"
    DESKTOP_DIR="/usr/share/applications"
    ICON_DIR="/usr/share/icons/hicolor/scalable/apps"
    echo "[*] Modo de instalación: Sistema (/opt y /usr/local/bin)"
else
    INSTALL_MODE="user"
    PREFIX="$HOME/.local/share/crosshairx-linux"
    BIN_DIR="$HOME/.local/bin"
    DESKTOP_DIR="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
    echo "[*] Modo de instalación: Usuario local ($HOME/.local)"
fi

echo ""
echo "[1/4] Comprobando dependencias..."

# Comprobar Python 3
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 no está instalado. Por favor instálalo primero."
    exit 1
fi

# Comprobar PyQt6
if ! python3 -c "import PyQt6" &>/dev/null; then
    echo "[AVISO] PyQt6 no parece estar instalado en Python 3."
    echo "  -> En Fedora: sudo dnf install python3-pyqt6"
    echo "  -> En Ubuntu/Debian: sudo apt install python3-pyqt6"
    echo "  -> En Arch: sudo pacman -S python-pyqt6"
    echo "  -> O mediante pip: pip install PyQt6"
    read -rp "¿Deseas continuar de todas formas? [s/N]: " RESP
    if [[ ! "$RESP" =~ ^[sS]$ ]]; then
        exit 1
    fi
fi

# Comprobar si el binario crosshair-overlay funciona o necesita compilarse
REBUILD=0
if [ ! -f "$DIR/build/crosshair-overlay" ]; then
    REBUILD=1
elif ! ldd "$DIR/build/crosshair-overlay" &>/dev/null; then
    echo "[AVISO] El binario precompilado no encuentra todas las bibliotecas de este sistema."
    REBUILD=1
fi

if [ "${1:-}" == "--rebuild" ] || [ "${1:-}" == "--compile" ]; then
    REBUILD=1
fi

if [ "$REBUILD" -eq 1 ]; then
    echo ""
    echo "[*] Compilando el renderizador 'crosshair-overlay' para este sistema..."
    if command -v cmake &>/dev/null && command -v g++ &>/dev/null; then
        (
            cd "$DIR"
            ./build.sh
        )
        echo "[OK] Compilación completada con éxito."
    else
        echo "[ERROR] Se requiere 'cmake' y 'g++' junto con las librerías de desarrollo:"
        echo "  - Fedora: sudo dnf install -y cmake gcc-c++ qt6-qtbase-devel layer-shell-qt-devel kf6-kglobalaccel-devel kf6-kwindowsystem-devel"
        echo "  - Ubuntu/Debian: sudo apt install -y cmake g++ qt6-base-dev liblayershellqt-dev libkf6globalaccel-dev libkf6windowsystem-dev"
        echo "  - Arch: sudo pacman -S --needed cmake gcc qt6-base layer-shell-qt kglobalaccel kwindowsystem"
        exit 1
    fi
fi

echo ""
echo "[2/4] Copiando archivos a $PREFIX..."
mkdir -p "$PREFIX/build"
mkdir -p "$BIN_DIR"
mkdir -p "$DESKTOP_DIR"
mkdir -p "$ICON_DIR"

cp -f "$DIR/crosshair.py" "$PREFIX/"
cp -f "$DIR/crosshairx-linux.svg" "$PREFIX/"
cp -f "$DIR/crosshairx-tray.svg" "$PREFIX/"
cp -rf "$DIR/overlay" "$PREFIX/"
cp -f "$DIR/build/crosshair-overlay" "$PREFIX/build/"
chmod +x "$PREFIX/crosshair.py"
chmod +x "$PREFIX/build/crosshair-overlay"

echo ""
echo "[3/4] Creando lanzador ejecutable en $BIN_DIR..."
cat << 'EOF' > "$BIN_DIR/crosshairx-linux"
#!/usr/bin/env bash
TARGET_DIR="__TARGET_DIR__"
exec /usr/bin/python3 "$TARGET_DIR/crosshair.py" "$@"
EOF
sed -i "s|__TARGET_DIR__|$PREFIX|g" "$BIN_DIR/crosshairx-linux"
chmod +x "$BIN_DIR/crosshairx-linux"

echo ""
echo "[4/4] Instalando icono y acceso directo del sistema..."
cp -f "$DIR/crosshairx-linux.svg" "$ICON_DIR/crosshairx-linux.svg"

cat << EOF > "$DESKTOP_DIR/crosshairx-linux.desktop"
[Desktop Entry]
Type=Application
Name=CrosshairX para Linux
Comment=Mira configurable para juegos
Exec=$BIN_DIR/crosshairx-linux
Icon=crosshairx-linux
Terminal=false
Categories=Game;Utility;
StartupWMClass=crosshairx-linux
EOF
chmod +x "$DESKTOP_DIR/crosshairx-linux.desktop"

# Actualizar base de datos de escritorios e iconos
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$(dirname "$ICON_DIR")" 2>/dev/null || true
fi

echo ""
echo "=========================================================="
echo "   ¡Instalación de CrosshairX completada exitosamente!    "
echo "=========================================================="
echo "Puedes iniciar la aplicación:"
echo " 1. Desde tu menú de aplicaciones buscando 'CrosshairX para Linux'."
echo " 2. O ejecutando desde la terminal: crosshairx-linux"
echo ""
