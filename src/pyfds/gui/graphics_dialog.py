"""Hardware & Graphics Settings (Run menu): how many processors FDS may use, and how the 3D view is drawn.

FDS runs on the CPU (OpenMP threads inside a mesh, MPI processes across meshes); the graphics card is only used by the
3D view. So this dialog holds the two FDS compute settings and the 3D view's anti-aliasing, and shows what graphics hardware
the view found. Everything goes through ``api`` (``api.sim`` for OpenMP, ``api.preferences`` for MPI).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox, QSpinBox, QVBoxLayout, QWidget,
)

#: (key, label) for the 3D view's anti-aliasing; the viewport understands these keys.
AA_MODES = [("off", "Off"), ("fxaa", "FXAA (fast, slightly soft)"), ("msaa4", "MSAA 4x"), ("msaa8", "MSAA 8x")]
SETTING_KEY = "graphics/antialiasing"


class HardwareSettingsDialog(QDialog):
    def __init__(self, api: Any, viewport: Any = None, parent: Optional[QWidget] = None, settings: Any = None,
                 cpu_count: Optional[int] = None) -> None:
        super().__init__(parent)
        self.api = api
        self.viewport = viewport
        if settings is None:
            from PySide6.QtCore import QSettings
            settings = QSettings("PyFDS", "PyFDS")
        self.settings = settings
        self.setWindowTitle("Hardware && Graphics Settings".replace("&&", "&"))
        self.resize(520, 360)
        v = QVBoxLayout(self)
        form = QFormLayout()
        v.addLayout(form)
        cpus = cpu_count or os.cpu_count() or 1
        form.addRow("Processors in this computer", QLabel(str(cpus), self))
        self.openmp = QSpinBox(self)
        self.openmp.setRange(0, 1024)
        self.openmp.setSpecialValueText("Automatic")
        self.openmp.setToolTip("OPENMP_THREADS in &MISC: threads FDS uses inside each mesh. Automatic lets FDS decide.")
        self.openmp.setValue(int(api.sim.values("environment").get("openmp_threads") or 0))
        form.addRow("OpenMP threads per mesh", self.openmp)
        self.mpi = QSpinBox(self)
        self.mpi.setRange(1, 4096)
        self.mpi.setToolTip("Processes a new parallel run starts with (one or more meshes per process)")
        self.mpi.setValue(int(api.preferences.get("default_mpi_processes") or 1))
        form.addRow("MPI processes for a new run", self.mpi)
        self.aa = QComboBox(self)
        for key, label in AA_MODES:
            self.aa.addItem(label, key)
        saved = str(settings.value(SETTING_KEY, "off") or "off")
        self.aa.setCurrentIndex(max(0, self.aa.findData(saved)))
        form.addRow("3D view anti-aliasing", self.aa)
        info = self._graphics_text()
        self.graphics = QLabel(info, self)
        self.graphics.setWordWrap(True)
        form.addRow("Graphics hardware", self.graphics)
        note = QLabel("FDS itself does not use the graphics card; it only draws the 3D view.", self)
        note.setStyleSheet("color: #6b7280;")
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch(1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Apply).clicked.connect(lambda: self._apply_quietly())
        v.addWidget(self.buttons)

    def _graphics_text(self) -> str:
        info: Dict[str, str] = {}
        if self.viewport is not None and hasattr(self.viewport, "opengl_info"):
            try:
                info = self.viewport.opengl_info() or {}
            except Exception as exc:                                   # a driver that will not answer is not a reason to fail
                return f"could not be read ({exc})"
        if not info:
            return "The 3D view is not available here."
        return f"{info.get('renderer', '?')}  ({info.get('vendor', '?')}), OpenGL {info.get('version', '?')}"

    # -- values and apply -------------------------------------------------------------------------------------------
    def antialiasing(self) -> str:
        return self.aa.currentData()

    def apply(self) -> Dict[str, Any]:
        """Save the settings (the OpenMP and MPI numbers as one undo step each, anti-aliasing for the next sessions too).
        Raises ``ValueError`` if a number is refused."""
        done: Dict[str, Any] = {}
        threads = self.openmp.value() or None
        if threads != (self.api.sim.values("environment").get("openmp_threads") or None):
            self.api.sim.update("environment", openmp_threads=threads)
            done["openmp_threads"] = threads
        if self.mpi.value() != self.api.preferences.get("default_mpi_processes"):
            self.api.preferences.set("default_mpi_processes", self.mpi.value())
            done["default_mpi_processes"] = self.mpi.value()
        if self.antialiasing() != str(self.settings.value(SETTING_KEY, "off") or "off"):
            self.settings.setValue(SETTING_KEY, self.antialiasing())
            done["antialiasing"] = self.antialiasing()
        if self.viewport is not None and hasattr(self.viewport, "set_antialiasing"):
            self.viewport.set_antialiasing(self.antialiasing())
        return done

    def _apply_quietly(self) -> bool:
        try:
            self.apply()
            return True
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return False

    def _on_ok(self) -> None:
        if self._apply_quietly():
            self.accept()
