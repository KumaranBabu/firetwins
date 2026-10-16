"""Keyboard shortcut customisation on the main window (UI-21): kept between sessions, edited in Help > Keyboard Shortcuts."""
from __future__ import annotations

from typing import Optional

from pyfds.gui.actions.keymap import Keymap

_KEY = "keymap/overrides"


class ActionsKeymapMixin:
    @property
    def keymap(self) -> Keymap:
        """The window's shortcuts (built from the menus on first use, so call after the menus exist)."""
        if "_keymap" not in self.__dict__:
            self._keymap = Keymap(self.menuBar())
        return self._keymap

    def restore_keymap(self) -> int:
        """Apply the shortcuts saved by an earlier session; returns how many were changed."""
        from PySide6.QtCore import QSettings
        return self.keymap.apply_json(str(QSettings("PyFDS", "PyFDS").value(_KEY, "") or ""))

    def save_keymap(self, keymap: Optional[Keymap] = None) -> None:
        from PySide6.QtCore import QSettings
        QSettings("PyFDS", "PyFDS").setValue(_KEY, (keymap or self.keymap).to_json())

    def _on_keyboard_shortcuts(self) -> None:
        from pyfds.gui.keymap_dialog import KeymapDialog
        KeymapDialog(self.keymap, on_save=self.save_keymap, parent=self).exec()
