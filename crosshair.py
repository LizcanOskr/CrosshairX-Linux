#!/usr/bin/env python3
"""Configuración y bandeja de CrosshairX para Linux."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSignalBlocker
from PyQt6.QtGui import (
    QAction, QColor, QKeySequence, QPainter, QPen, QPixmap, QIcon,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QPushButton, QKeySequenceEdit, QSlider, QSpinBox, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)


APP_DIR = Path(__file__).resolve().parent
SETTINGS_DIR = Path.home() / ".config" / "crosshairx-linux"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


def find_overlay_binary() -> Path:
    candidates = [
        APP_DIR / "build" / "crosshair-overlay",
        APP_DIR / "crosshair-overlay",
        Path("/usr/lib/crosshairx-linux/crosshair-overlay"),
        Path("/usr/libexec/crosshairx-linux/crosshair-overlay"),
        Path("/usr/bin/crosshair-overlay"),
        Path("/usr/local/bin/crosshair-overlay"),
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    return APP_DIR / "build" / "crosshair-overlay"


OVERLAY_BINARY = find_overlay_binary()
DEFAULTS = {
    "version": 4, "shape": "Cruz", "color": "#00ff66", "size": 48,
    "gap": 5, "thickness": 1.5, "outline": True, "visible": True,
    "screen": 0, "x_offset": 0, "y_offset": 0, "tray_symbol_scale": 100,
    "move_left_shortcut": "Home", "move_right_shortcut": "End",
    "move_up_shortcut": "PgUp", "move_down_shortcut": "PgDown",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CrosshairX para Linux")
        icon_path = APP_DIR / "crosshairx-linux.svg"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            self.setWindowIcon(QIcon.fromTheme("crosshairx-linux"))
        self.setMinimumWidth(430)
        self.settings = self.load_settings()
        self.screens = QApplication.screens()
        self.overlay_process = None
        self._loading_settings = False
        self._quitting = False
        self.tray = None
        self.toggle_action = None
        self._build_ui()
        self.apply_settings()
        self._make_tray()
        self.save_settings()
        self.start_overlay()
        self.position_sync_timer = QTimer(self)
        self.position_sync_timer.timeout.connect(self.sync_from_overlay)
        self.position_sync_timer.start(100)

    @staticmethod
    def load_settings():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            version = int(data.get("version", 1))
            if version < 2:
                # En la primera versión el tamaño representaba cada brazo.
                data["size"] = min(256, max(1, int(data.get("size", 24)) * 2))
            data.setdefault("x_offset", 0)
            data.setdefault("y_offset", 0)
            data.setdefault("tray_symbol_scale", 100)
            for key in ("move_left_shortcut", "move_right_shortcut",
                        "move_up_shortcut", "move_down_shortcut"):
                if not isinstance(data.get(key, DEFAULTS[key]), str):
                    data[key] = DEFAULTS[key]
            data["version"] = 4
            return {**DEFAULTS, **data}
        except (OSError, ValueError, TypeError):
            return DEFAULTS.copy()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        heading = QLabel("CrosshairX para Linux")
        heading.setStyleSheet("font-size:20px;font-weight:700")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Superposición de Plasma, sin ventana normal."))

        form = QFormLayout()
        self.shape = QComboBox()
        self.shape.addItems(["Cruz", "Punto", "Círculo", "T"])
        self.color_button = QPushButton("Elegir color…")
        self.color_button.clicked.connect(self.pick_color)

        self.size = self._spin(1, 256)
        self.size.setSuffix(" px")
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(1, 256)
        self.size_slider.valueChanged.connect(self.size.setValue)
        self.size.valueChanged.connect(self.size_slider.setValue)
        size_controls = QWidget()
        size_layout = QHBoxLayout(size_controls)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(self.size_slider, 1)
        size_layout.addWidget(self.size)

        self.gap = self._spin(0, 128)
        self.gap.setSuffix(" px")
        self.thickness = QDoubleSpinBox()
        self.thickness.setRange(0.25, 8.0)
        self.thickness.setDecimals(2)
        self.thickness.setSingleStep(0.25)
        self.thickness.setSuffix(" px")

        self.screen = QComboBox()
        for index, screen in enumerate(self.screens):
            geometry = screen.geometry()
            self.screen.addItem(
                f"{index + 1}. {screen.name()} — "
                f"{geometry.width()} × {geometry.height()} px", index)
        if len(self.screens) == 1:
            self.screen.setToolTip(
                "Qt/Wayland detecta una pantalla activa. El selector permite "
                "elegir entre las pantallas que Plasma expone a la aplicación.")
        elif not self.screens:
            self.screen.addItem("No se detectaron pantallas", 0)

        self.x_offset = self._spin(-8192, 8192)
        self.x_offset.setSuffix(" px")
        self.y_offset = self._spin(-8192, 8192)
        self.y_offset.setSuffix(" px")
        self.center_button = QPushButton("Centrar en la pantalla")
        self.center_button.clicked.connect(self.center_crosshair)
        self.move_shortcuts = {}
        self.shortcut_warning = QLabel()
        self.shortcut_warning.setStyleSheet("color:#d9534f;font-size:11px")
        self.shortcut_warning.setWordWrap(True)
        shortcut_form = QFormLayout()
        for key, label in (
            ("move_left_shortcut", "Izquierda"),
            ("move_right_shortcut", "Derecha"),
            ("move_up_shortcut", "Arriba"),
            ("move_down_shortcut", "Abajo"),
        ):
            shortcut = QKeySequenceEdit(QKeySequence(DEFAULTS[key]))
            shortcut.setMaximumSequenceLength(1)
            shortcut.setToolTip(
                "Pulsa este campo y luego la combinación de teclas que quieras."
            )
            self.move_shortcuts[key] = shortcut
            shortcut_form.addRow(label, shortcut)
        position = QWidget()
        position_layout = QVBoxLayout(position)
        position_layout.setContentsMargins(0, 0, 0, 0)
        axes = QHBoxLayout()
        axes.addWidget(QLabel("X"))
        axes.addWidget(self.x_offset)
        axes.addWidget(QLabel("Y"))
        axes.addWidget(self.y_offset)
        position_layout.addLayout(axes)
        position_layout.addWidget(self.center_button)
        position_layout.addWidget(QLabel("Atajos globales para mover la mira:"))
        position_layout.addLayout(shortcut_form)
        position_layout.addWidget(self.shortcut_warning)
        position_layout.addWidget(QLabel(
            "Cada atajo desplaza la mira 1 px en la dirección indicada."
        ))
        position_layout.addWidget(QLabel(
            "Pulsa Ctrl + Alt + º para activar o desactivar la mira."
        ))

        self.outline = QCheckBox("Borde negro para mejorar el contraste")
        self.visible = QCheckBox("Mostrar la mira")
        self.tray_scale = self._spin(30, 100)
        self.tray_scale.setSuffix(" %")

        form.addRow("Forma", self.shape)
        form.addRow("Color", self.color_button)
        form.addRow("Tamaño total", size_controls)
        form.addRow("Separación", self.gap)
        form.addRow("Grosor", self.thickness)
        form.addRow("Pantalla activa", self.screen)
        form.addRow("Posición desde el centro", position)
        form.addRow("Símbolo en la bandeja", self.tray_scale)
        form.addRow("", self.outline)
        form.addRow("", self.visible)
        layout.addLayout(form)

        self.preview = QFrame()
        self.preview.setMinimumHeight(82)
        self.preview.setStyleSheet("background:#20242a;border-radius:8px")
        preview_layout = QVBoxLayout(self.preview)
        self.preview_label = QLabel("＋")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("color:#00ff66;font-size:28px;border:0")
        preview_layout.addWidget(self.preview_label)
        layout.addWidget(self.preview)

        note = QLabel("La mira usa la capa superpuesta de KDE Plasma: queda por "
                      "encima del escritorio, no recibe clics y no reserva espacio "
                      "para el dock ni la barra superior.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#818995;font-size:11px")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        self.toggle_button = QPushButton("Desactivar mira")
        self.toggle_button.clicked.connect(self.toggle_visible)
        buttons.addWidget(self.toggle_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.setCentralWidget(root)

        for control in (self.shape, self.size, self.gap, self.thickness,
                        self.screen, self.x_offset, self.y_offset,
                        self.tray_scale, self.outline, self.visible,
                        *self.move_shortcuts.values()):
            if isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self.changed)
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.valueChanged.connect(self.changed)
            elif isinstance(control, QKeySequenceEdit):
                control.keySequenceChanged.connect(self.changed)
            else:
                control.stateChanged.connect(self.changed)

    @staticmethod
    def _spin(low, high):
        spin = QSpinBox()
        spin.setRange(low, high)
        return spin

    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("CrosshairX para Linux")
        menu = QMenu()
        open_settings = QAction("Abrir configuración", self)
        open_settings.triggered.connect(self.open_settings)
        menu.addAction(open_settings)
        self.toggle_action = QAction(self)
        self.toggle_action.triggered.connect(self.toggle_visible)
        menu.addAction(self.toggle_action)
        menu.addSeparator()
        quit_action = QAction("Cerrar aplicación", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self._update_tray_action()
        self._update_tray_icon()
        self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        self.visible.setChecked(not self.visible.isChecked())

    def _update_tray_action(self):
        if self.toggle_action:
            self.toggle_action.setText("Desactivar mira" if self.visible.isChecked()
                                       else "Activar mira")

    def _update_tray_icon(self):
        if not self.tray:
            return
        canvas = QPixmap(64, 64)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = self.tray_scale.value() / 100.0
        reach = 22 * scale
        width = max(1.0, 4 * scale)
        pen = QPen(QColor("white"), width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)
        center = 32
        inner = max(3.0, 7 * scale)
        for x1, y1, x2, y2 in (
            (center - reach, center, center - inner, center),
            (center + inner, center, center + reach, center),
            (center, center - reach, center, center - inner),
            (center, center + inner, center, center + reach),
        ):
            painter.drawLine(round(x1), round(y1), round(x2), round(y2))
        painter.end()
        self.tray.setIcon(QIcon(canvas))

    def open_settings(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def apply_settings(self):
        self._loading_settings = True
        s = self.settings
        self.shape.setCurrentText(s["shape"])
        self.size.setValue(int(s["size"]))
        self.gap.setValue(int(s["gap"]))
        self.thickness.setValue(float(s["thickness"]))
        self.outline.setChecked(bool(s["outline"]))
        self.visible.setChecked(bool(s["visible"]))
        self.screen.setCurrentIndex(min(int(s["screen"]), max(0, self.screen.count() - 1)))
        self.x_offset.setValue(int(s["x_offset"]))
        self.y_offset.setValue(int(s["y_offset"]))
        self.tray_scale.setValue(int(s["tray_symbol_scale"]))
        for key, shortcut in self.move_shortcuts.items():
            shortcut.setKeySequence(QKeySequence(s[key]))
        self._loading_settings = False
        self._update_controls()

    def changed(self, *_):
        if self._loading_settings:
            return
        shortcut_sequences = [
            shortcut.keySequence().toString(
                QKeySequence.SequenceFormat.PortableText)
            for shortcut in self.move_shortcuts.values()
        ]
        assigned_sequences = [sequence for sequence in shortcut_sequences if sequence]
        if len(assigned_sequences) != len(set(assigned_sequences)):
            self.shortcut_warning.setText(
                "Cada dirección debe tener una combinación distinta."
            )
            return
        self.shortcut_warning.clear()
        # El overlay puede haber desplazado la mira con un atajo global.
        # Conserva esa posición al guardar cualquier otro control.
        if self.sender() not in (self.x_offset, self.y_offset):
            try:
                current = json.loads(SETTINGS_FILE.read_text())
                self.x_offset.setValue(int(current.get("x_offset", self.x_offset.value())))
                self.y_offset.setValue(int(current.get("y_offset", self.y_offset.value())))
                if self.sender() is not self.visible:
                    self.visible.setChecked(bool(current.get("visible", self.visible.isChecked())))
            except (OSError, ValueError, TypeError):
                pass
        self.settings = {
            "version": 4,
            "shape": self.shape.currentText(),
            "color": self.settings["color"],
            "size": self.size.value(),
            "gap": self.gap.value(),
            "thickness": self.thickness.value(),
            "outline": self.outline.isChecked(),
            "visible": self.visible.isChecked(),
            "screen": self.screen.currentIndex(),
            "x_offset": self.x_offset.value(),
            "y_offset": self.y_offset.value(),
            "tray_symbol_scale": self.tray_scale.value(),
            **{
                key: shortcut.keySequence().toString(
                    QKeySequence.SequenceFormat.PortableText)
                for key, shortcut in self.move_shortcuts.items()
            },
        }
        self._update_controls()
        self.save_settings()

    def sync_from_overlay(self):
        try:
            current = json.loads(SETTINGS_FILE.read_text())
            x = int(current.get("x_offset", self.x_offset.value()))
            y = int(current.get("y_offset", self.y_offset.value()))
            visible = bool(current.get("visible", self.visible.isChecked()))
        except (OSError, ValueError, TypeError):
            return
        if (x == self.x_offset.value() and y == self.y_offset.value()
                and visible == self.visible.isChecked()):
            return
        self._loading_settings = True
        try:
            self.x_offset.setValue(x)
            self.y_offset.setValue(y)
            self.visible.setChecked(visible)
            self.settings["x_offset"] = self.x_offset.value()
            self.settings["y_offset"] = self.y_offset.value()
            self.settings["visible"] = self.visible.isChecked()
            self._update_controls()
        finally:
            self._loading_settings = False

    def _update_controls(self):
        self.toggle_button.setText("Desactivar mira" if self.visible.isChecked()
                                   else "Activar mira")
        self._update_tray_action()
        self._update_tray_icon()
        self.preview_label.setStyleSheet(
            f"color:{self.settings['color']};font-size:28px;border:0")
        self.preview_label.setText({"Cruz": "＋", "Punto": "●",
                                    "Círculo": "◎", "T": "T"}
                                   [self.shape.currentText()])

    def center_crosshair(self):
        self.x_offset.setValue(0)
        self.y_offset.setValue(0)

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.settings["color"]), self,
                                      "Elige el color de la mira")
        if color.isValid():
            self.settings["color"] = color.name()
            self.changed()

    def save_settings(self):
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2, ensure_ascii=False))

    def start_overlay(self):
        if not OVERLAY_BINARY.is_file():
            QMessageBox.critical(
                self, "Falta el renderizador de Plasma",
                "No encuentro build/crosshair-overlay. Compila el renderizador "
                "con ./build.sh y vuelve a abrir la aplicación.")
            return
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "wayland"
        env["QT_WAYLAND_SHELL_INTEGRATION"] = "layer-shell"
        try:
            self.overlay_process = subprocess.Popen(
                [str(OVERLAY_BINARY), str(SETTINGS_FILE)],
                cwd=str(APP_DIR), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            QTimer.singleShot(1200, self.check_overlay)
        except OSError as error:
            QMessageBox.critical(self, "No se pudo iniciar la mira", str(error))

    def check_overlay(self):
        if (self.overlay_process and self.overlay_process.poll() is not None
                and not self._quitting):
            QMessageBox.critical(
                self, "No se pudo iniciar la capa de Plasma",
                "El renderizador terminó al iniciarse. Comprueba que la sesión "
                "sea KDE Plasma Wayland y que LayerShellQt esté instalado.")

    def closeEvent(self, event):
        self.save_settings()
        if self._quitting:
            event.accept()
        elif self.tray:
            self.hide()
            event.ignore()
        else:
            self.quit_app()
            event.accept()

    def quit_app(self):
        self._quitting = True
        self.settings["visible"] = False
        self.save_settings()
        if self.overlay_process and self.overlay_process.poll() is None:
            self.overlay_process.terminate()
            try:
                self.overlay_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.overlay_process.kill()
        if self.tray:
            self.tray.hide()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("crosshairx-linux")
    app.setApplicationDisplayName("CrosshairX para Linux")
    app.setDesktopFileName("crosshairx-linux")
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
