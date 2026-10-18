"""View menu actions: camera, display, bookmarks, window layouts."""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QInputDialog, QMessageBox

from pyfds.core.viewport import CameraPreset, VisibilityFlags


class ActionsViewMixin:
    def _on_toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_save_bookmark(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Bookmark", "Bookmark name:")
        if not ok or not name:
            return
        self._view_bookmarks[name] = self.api.viewport.state.camera
        self.statusBar().showMessage(f"View saved as bookmark {name!r}.")

    def _on_load_bookmark(self) -> None:
        if not self._view_bookmarks:
            QMessageBox.information(self, "No bookmarks", "No saved views yet — use Save Bookmark first.")
            return
        name, ok = QInputDialog.getItem(
            self, "Load Bookmark", "View:", list(self._view_bookmarks.keys()), 0, False
        )
        if not ok or not name:
            return
        self.api.viewport.set_camera(self._view_bookmarks[name])

    def _on_reset_view(self) -> None:
        if hasattr(self.viewport_widget, "reset_view"):
            self.viewport_widget.reset_view()

    def _on_camera_preset(self, preset: CameraPreset) -> None:
        if hasattr(self.viewport_widget, "apply_preset"):
            self.viewport_widget.apply_preset(preset)

    def _on_toggle_wireframe(self, checked: bool) -> None:
        if hasattr(self.viewport_widget, "toggle_wireframe"):
            self.viewport_widget.toggle_wireframe()

    def _on_toggle_visibility(self, flag: VisibilityFlags, visible: bool) -> None:
        if hasattr(self.viewport_widget, "set_visibility"):
            self.viewport_widget.set_visibility(flag, visible)

    def _window_layout_names(self) -> list:
        settings = QSettings("PyFDS", "PyFDS")
        names = settings.value("window_layout_names", [])
        if isinstance(names, str):
            names = [names]
        return list(names or [])

    def _on_workspace(self) -> None:
        """Save the current window layout (dock/toolbar arrangement) under a name."""
        name, ok = QInputDialog.getText(self, "Save Workspace", "Layout name:")
        if not ok or not name:
            return
        settings = QSettings("PyFDS", "PyFDS")
        names = self._window_layout_names()
        if name not in names:
            names.append(name)
            settings.setValue("window_layout_names", names)
        settings.setValue(f"window_layout/{name}", self.saveState())
        self.statusBar().showMessage(f"Window layout saved as {name!r}.")

    def _on_layouts(self) -> None:
        """Apply a previously saved named window layout."""
        names = self._window_layout_names()
        if not names:
            QMessageBox.information(
                self, "No layouts", "No saved layouts yet — use Workspace to save one first."
            )
            return
        name, ok = QInputDialog.getItem(self, "Load Layout", "Layout:", names, 0, False)
        if not ok or not name:
            return
        state = QSettings("PyFDS", "PyFDS").value(f"window_layout/{name}")
        if state is None:
            QMessageBox.warning(self, "Layout not found", f"No saved layout named {name!r}.")
            return
        self.restoreState(state)
        self.statusBar().showMessage(f"Window layout {name!r} restored.")

    def _on_reset_window_layout(self) -> None:
        """Restore docks/toolbars to their state at application startup."""
        self.restoreState(self._default_window_state)
        self._layout_was_reset()
        self.statusBar().showMessage("Window layout reset to default.")
